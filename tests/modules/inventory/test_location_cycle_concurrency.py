import asyncio
import os

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio

CONCURRENCY_TEST_DATABASE_URL = os.getenv("CONCURRENCY_TEST_DATABASE_URL")
if not CONCURRENCY_TEST_DATABASE_URL:
    pytest.skip(
        "CONCURRENCY_TEST_DATABASE_URL environment variable must be explicitly declared "
        "to run isolated concurrency tests.",
        allow_module_level=True,
    )

EXPECTED_DB = "fireassets_concurrency_test"

CYCLE_DETECTION_SQL = """
WITH RECURSIVE paths(current_asset_id, path, cycle) AS (
    SELECT u.bien_contenedor_id,
           ARRAY[b.id, u.bien_contenedor_id],
           u.bien_contenedor_id = b.id
    FROM bienes b
    JOIN ubicaciones u ON u.id = b.ubicacion_id
    WHERE u.bien_contenedor_id IS NOT NULL
    UNION ALL
    SELECT u.bien_contenedor_id,
           paths.path || u.bien_contenedor_id,
           u.bien_contenedor_id = ANY(paths.path)
    FROM paths
    JOIN bienes b ON b.id = paths.current_asset_id
    JOIN ubicaciones u ON u.id = b.ubicacion_id
    WHERE NOT paths.cycle
      AND u.bien_contenedor_id IS NOT NULL
)
SELECT current_asset_id, path, cycle FROM paths WHERE cycle;
"""


async def get_verified_temp_conn() -> asyncpg.Connection:
    assert CONCURRENCY_TEST_DATABASE_URL is not None
    conn = await asyncpg.connect(CONCURRENCY_TEST_DATABASE_URL)
    current_db = await conn.fetchval("SELECT current_database()")
    if current_db != EXPECTED_DB:
        await conn.close()
        raise RuntimeError(
            f"SAFETY GUARD: Concurrency tests require {EXPECTED_DB}, but connected to {current_db}!"
        )
    return conn


@pytest_asyncio.fixture
async def setup_temp_db():
    conn = await get_verified_temp_conn()
    await conn.execute("DELETE FROM auditoria_cambios;")
    await conn.execute("DELETE FROM movimientos;")
    await conn.execute("UPDATE bienes SET ubicacion_id = NULL;")
    await conn.execute("DELETE FROM ubicaciones;")
    await conn.execute("DELETE FROM bienes;")
    await conn.execute("DELETE FROM categorias;")
    await conn.execute("DELETE FROM usuarios;")
    await conn.execute("DELETE FROM roles;")

    await conn.execute(
        "INSERT INTO roles (id, nombre, descripcion, activo) VALUES "
        "(1, 'ADMINISTRADOR', 'Admin', true), (2, 'SUPERVISOR', 'Supervisor', true);"
    )
    await conn.execute(
        "INSERT INTO usuarios (id, email, password_hash, rol_id, activo) VALUES "
        "(1, 'test@example.com', 'hash', 2, true);"
    )
    await conn.execute(
        "INSERT INTO categorias (id, nombre) VALUES (1, 'Vehículos'), (2, 'Herramientas');"
    )
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_observable_lock_contention_and_cross_transfer(setup_temp_db):
    """
    Scenario 1: Cross transfer A->B and B->A with observable lock contention in pg_locks.
    Verifies that T2 (identified by its specific backend PID) is actively suspended on the
    specific advisory lock key (granted=false) while T1 holds it, and upon T1 commit,
    T2 unblocks and is rejected with SQLSTATE 23514.
    """
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    b_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('B', 'B', 1) RETURNING id;"
    )
    loc_b = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc B', 'VEHICULO', $1, true) RETURNING id;",
        b_id,
    )

    t1_holds_lock = asyncio.Event()
    t1_can_commit = asyncio.Event()
    t2_pid_ready = asyncio.Event()
    t2_backend_pid: int | None = None
    results: dict[str, dict[str, str | bool | None]] = {}

    async def task_t1():
        conn = await get_verified_temp_conn()
        res: dict[str, str | bool | None] = {
            "tx": "T1",
            "committed": False,
            "sqlstate": None,
        }
        tr = conn.transaction()
        try:
            await tr.start()
            await conn.fetchrow("SELECT * FROM bienes WHERE id = $1 FOR UPDATE", a_id)
            await conn.execute(
                "INSERT INTO movimientos (bien_id, usuario_id, tipo_movimiento, ubicacion_destino_id, motivo) "
                "VALUES ($1, 1, 'TRASLADO', $2, 'Observable Contention Test')",
                a_id,
                loc_b,
            )
            # Fires trigger and acquires advisory lock
            await conn.execute(
                "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", loc_b, a_id
            )
            t1_holds_lock.set()

            # Wait until T2 is confirmed actively waiting for this specific advisory lock in pg_locks
            await asyncio.wait_for(t1_can_commit.wait(), timeout=5.0)
            await tr.commit()
            res["committed"] = True
        except asyncpg.PostgresError as e:
            res["error"] = str(e)
            res["sqlstate"] = getattr(e, "sqlstate", None)
            try:
                await tr.rollback()
            except asyncpg.PostgresError:
                pass
        finally:
            await conn.close()
            results["T1"] = res

    async def task_t2():
        nonlocal t2_backend_pid
        conn = await get_verified_temp_conn()
        t2_backend_pid = await conn.fetchval("SELECT pg_backend_pid()")
        t2_pid_ready.set()

        res: dict[str, str | bool | None] = {
            "tx": "T2",
            "committed": False,
            "sqlstate": None,
        }
        tr = conn.transaction()
        try:
            await tr.start()
            # Wait for T1 to acquire the advisory lock
            await t1_holds_lock.wait()
            await conn.fetchrow("SELECT * FROM bienes WHERE id = $1 FOR UPDATE", b_id)
            await conn.execute(
                "INSERT INTO movimientos (bien_id, usuario_id, tipo_movimiento, ubicacion_destino_id, motivo) "
                "VALUES ($1, 1, 'TRASLADO', $2, 'Observable Contention Test')",
                b_id,
                loc_a,
            )

            # Launch UPDATE asynchronously; it blocks inside trigger on advisory lock
            update_coro = conn.execute(
                "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", loc_a, b_id
            )
            update_task = asyncio.create_task(update_coro)

            # Poll pg_locks specifically for T2 PID, single-bigint advisory lock (objsubid=1),
            # ExclusiveLock mode, and exact key matching hashtext('prevent_location_containment_cycles')::bigint
            blocked_observed = False
            for _ in range(50):
                await asyncio.sleep(0.02)
                is_waiting = await admin_conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_locks
                        WHERE pid = $1
                          AND locktype = 'advisory'
                          AND objsubid = 1
                          AND mode = 'ExclusiveLock'
                          AND NOT granted
                          AND ((classid::bigint << 32) | objid::bigint) = hashtext('prevent_location_containment_cycles')::bigint
                    );
                    """,
                    t2_backend_pid,
                )
                if is_waiting:
                    blocked_observed = True
                    break

            assert blocked_observed, (
                f"Process T2 (pid={t2_backend_pid}) was not observed waiting for expected advisory lock in pg_locks!"
            )

            # Signal T1 that it can commit and release the lock
            t1_can_commit.set()

            # Await T2 update: unblocks from lock, evaluates graph with fresh snapshot, raises 23514
            await update_task
            await tr.commit()
            res["committed"] = True
        except asyncpg.PostgresError as e:
            res["error"] = str(e)
            res["sqlstate"] = getattr(e, "sqlstate", None)
            try:
                await tr.rollback()
            except asyncpg.PostgresError:
                pass
        finally:
            await conn.close()
            results["T2"] = res

    await asyncio.gather(task_t1(), task_t2())

    assert results["T1"]["committed"] is True
    assert results["T2"]["committed"] is False
    assert results["T2"]["sqlstate"] == "23514"

    cycles = await admin_conn.fetch(CYCLE_DETECTION_SQL)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_three_way_ring_cycle_prevented(setup_temp_db):
    """Scenario 2: Three concurrent transfers A->B->C->A do not consolidate a ring."""
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    b_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('B', 'B', 1) RETURNING id;"
    )
    loc_b = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc B', 'VEHICULO', $1, true) RETURNING id;",
        b_id,
    )

    c_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('C', 'C', 1) RETURNING id;"
    )
    loc_c = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc C', 'VEHICULO', $1, true) RETURNING id;",
        c_id,
    )

    barrier = asyncio.Barrier(3)
    results: dict[str, dict[str, str | bool | None]] = {}

    async def transfer(tx_name: str, aid: int, lid: int):
        conn = await get_verified_temp_conn()
        res: dict[str, str | bool | None] = {
            "tx": tx_name,
            "committed": False,
            "sqlstate": None,
        }
        tr = conn.transaction()
        try:
            await tr.start()
            await conn.fetchrow("SELECT * FROM bienes WHERE id = $1 FOR UPDATE", aid)
            await conn.execute(
                "INSERT INTO movimientos (bien_id, usuario_id, tipo_movimiento, ubicacion_destino_id, motivo) "
                "VALUES ($1, 1, 'TRASLADO', $2, 'Scenario 2 Test')",
                aid,
                lid,
            )
            await asyncio.wait_for(barrier.wait(), timeout=5.0)
            await conn.execute(
                "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", lid, aid
            )
            await asyncio.sleep(0.05)
            await tr.commit()
            res["committed"] = True
        except asyncpg.PostgresError as e:
            res["error"] = str(e)
            res["sqlstate"] = getattr(e, "sqlstate", None)
            try:
                await tr.rollback()
            except asyncpg.PostgresError:
                pass
        finally:
            await conn.close()
            results[tx_name] = res

    await asyncio.gather(
        transfer("T1", a_id, loc_b),
        transfer("T2", b_id, loc_c),
        transfer("T3", c_id, loc_a),
    )

    committed = [v for v in results.values() if v["committed"]]
    rejected = [v for v in results.values() if not v["committed"]]
    assert len(committed) == 2, f"Expected 2 commits, got {len(committed)}"
    assert len(rejected) == 1, f"Expected 1 rejection, got {len(rejected)}"
    assert rejected[0]["sqlstate"] == "23514"

    cycles = await admin_conn.fetch(CYCLE_DETECTION_SQL)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_transfer_rejection_preserves_movement_history_atomicity(setup_temp_db):
    """Scenario 3: Failed transfer rolls back movements and leaves no orphan history."""
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    conn = await get_verified_temp_conn()
    tr = conn.transaction()
    await tr.start()
    rejected = False
    try:
        await conn.execute(
            "INSERT INTO movimientos (bien_id, usuario_id, tipo_movimiento, ubicacion_destino_id, motivo) "
            "VALUES ($1, 1, 'TRASLADO', $2, 'Self-containment test')",
            a_id,
            loc_a,
        )
        await conn.execute(
            "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", loc_a, a_id
        )
        await tr.commit()
    except asyncpg.PostgresError as e:
        rejected = True
        assert getattr(e, "sqlstate", None) == "23514"
        await tr.rollback()
    finally:
        await conn.close()

    assert rejected is True
    count = await admin_conn.fetchval(
        "SELECT count(*) FROM movimientos WHERE bien_id = $1", a_id
    )
    assert count == 0
    asset_loc = await admin_conn.fetchval(
        "SELECT ubicacion_id FROM bienes WHERE id = $1", a_id
    )
    assert asset_loc is None


@pytest.mark.asyncio
async def test_direct_sql_writes_protected_by_trigger_lock(setup_temp_db):
    """Scenario 4: Direct SQL writes bypassing API are serialized and validated."""
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    b_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('B', 'B', 1) RETURNING id;"
    )
    loc_b = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc B', 'VEHICULO', $1, true) RETURNING id;",
        b_id,
    )

    barrier = asyncio.Barrier(2)
    results: dict[str, dict[str, str | bool | None]] = {}

    async def raw_update(name: str, aid: int, lid: int):
        conn = await get_verified_temp_conn()
        res: dict[str, str | bool | None] = {
            "name": name,
            "committed": False,
            "sqlstate": None,
        }
        tr = conn.transaction()
        try:
            await tr.start()
            await barrier.wait()
            await conn.execute(
                "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", lid, aid
            )
            await asyncio.sleep(0.05)
            await tr.commit()
            res["committed"] = True
        except asyncpg.PostgresError as e:
            res["error"] = str(e)
            res["sqlstate"] = getattr(e, "sqlstate", None)
            try:
                await tr.rollback()
            except asyncpg.PostgresError:
                pass
        finally:
            await conn.close()
            results[name] = res

    await asyncio.gather(
        raw_update("Raw-1", a_id, loc_b),
        raw_update("Raw-2", b_id, loc_a),
    )

    committed = [v for v in results.values() if v["committed"]]
    assert len(committed) == 1
    cycles = await admin_conn.fetch(CYCLE_DETECTION_SQL)
    assert len(cycles) == 0


@pytest.mark.asyncio
async def test_repeatable_read_rejected_with_0a000(setup_temp_db):
    """
    Scenario 5: Demonstrates that REPEATABLE READ isolation is explicitly rejected
    by the defensive guard with SQLSTATE 0A000 before evaluating the graph.
    """
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    conn = await get_verified_temp_conn()
    tr = conn.transaction(isolation="repeatable_read")
    await tr.start()
    rejected = False
    sqlstate = None
    try:
        await conn.execute(
            "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", loc_a, a_id
        )
        await tr.commit()
    except asyncpg.PostgresError as e:
        rejected = True
        sqlstate = getattr(e, "sqlstate", None)
        assert "requires READ COMMITTED" in str(e)
        await tr.rollback()
    finally:
        await conn.close()

    assert rejected is True
    assert sqlstate == "0A000"


@pytest.mark.asyncio
async def test_serializable_rejected_with_0a000(setup_temp_db):
    """
    Scenario 6: Demonstrates that SERIALIZABLE isolation is explicitly rejected
    by the defensive guard with SQLSTATE 0A000 before evaluating the graph.
    """
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    conn = await get_verified_temp_conn()
    tr = conn.transaction(isolation="serializable")
    await tr.start()
    rejected = False
    sqlstate = None
    try:
        await conn.execute(
            "UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", loc_a, a_id
        )
        await tr.commit()
    except asyncpg.PostgresError as e:
        rejected = True
        sqlstate = getattr(e, "sqlstate", None)
        assert "requires READ COMMITTED" in str(e)
        await tr.rollback()
    finally:
        await conn.close()

    assert rejected is True
    assert sqlstate == "0A000"


@pytest.mark.asyncio
async def test_read_committed_preserves_expected_behavior(setup_temp_db):
    """
    Scenario 7: Verifies that READ COMMITTED operates smoothly for legitimate transfers.
    """
    admin_conn = setup_temp_db

    a_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('A', 'A', 1) RETURNING id;"
    )
    loc_a = await admin_conn.fetchval(
        "INSERT INTO ubicaciones (nombre, tipo_ubicacion, bien_contenedor_id, activa) VALUES ('Loc A', 'VEHICULO', $1, true) RETURNING id;",
        a_id,
    )

    b_id = await admin_conn.fetchval(
        "INSERT INTO bienes (codigo_interno, nombre, categoria_id) VALUES ('B', 'B', 1) RETURNING id;"
    )

    conn = await get_verified_temp_conn()
    tr = conn.transaction(isolation="read_committed")
    await tr.start()
    await conn.execute(
        "INSERT INTO movimientos (bien_id, usuario_id, tipo_movimiento, ubicacion_destino_id, motivo) "
        "VALUES ($1, 1, 'TRASLADO', $2, 'Valid placement')",
        b_id,
        loc_a,
    )
    await conn.execute("UPDATE bienes SET ubicacion_id = $1 WHERE id = $2", loc_a, b_id)
    await tr.commit()
    await conn.close()

    placed_loc = await admin_conn.fetchval(
        "SELECT ubicacion_id FROM bienes WHERE id = $1", b_id
    )
    assert placed_loc == loc_a

    movement_count = await admin_conn.fetchval(
        "SELECT count(*) FROM movimientos WHERE bien_id = $1", b_id
    )
    assert movement_count == 1
