from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.modules.auth.models import User
from app.modules.auth.validations.tokens import ACCESS_TOKEN_COOKIE, create_access_token
from app.modules.inventory.shared.models import Asset, Category, Location


async def create_category(session: AsyncSession) -> int:
    category = Category(nombre=f"Vehicle-{uuid4().hex}")
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category.id


async def create_asset(client: AsyncClient, category_id: int, **extra: object) -> dict:
    response = await client.post(
        "/inventory/assets",
        json={
            "internal_code": f"LOC-{uuid4().hex[:20]}",
            "name": "Vehicle or equipment",
            "category_id": category_id,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_test_user(session: AsyncSession) -> User:
    user = User(email=f"transfer-{uuid4().hex}@example.test", password_hash="test-only")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_physical_location_and_asset_assignment(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    client = authenticated_inventory_client
    created = await client.post(
        "/inventory/locations",
        json={
            "name": "Main depot",
            "location_type": "FISICA",
            "description": "North building",
        },
    )
    assert created.status_code == 201, created.text
    location = created.json()
    assert location["name"] == "Main depot"
    assert location["location_type"] == "FISICA"
    assert location["container_asset_id"] is None
    assert location["description"] == "North building"
    assert location["active"] is True
    assert location["created_at"] and location["updated_at"]

    asset = await create_asset(client, category_id, location_id=location["id"])
    assert asset["location_id"] == location["id"]
    assert (await client.get(f"/inventory/assets/{asset['id']}")).json()[
        "location_id"
    ] == location["id"]
    assert (
        await client.get(f"/inventory/locations/{location['id']}")
    ).json() == location


@pytest.mark.asyncio
async def test_vehicle_location_has_one_existing_container(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    client = authenticated_inventory_client
    vehicle = await create_asset(client, category_id)
    missing_id = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM bienes")
        )
    )
    missing = await client.post(
        "/inventory/locations",
        json={
            "name": "Missing engine",
            "location_type": "VEHICULO",
            "container_asset_id": missing_id,
        },
    )
    assert missing.status_code == 409
    response = await client.post(
        "/inventory/locations",
        json={
            "name": "Engine 2",
            "location_type": "VEHICULO",
            "container_asset_id": vehicle["id"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["container_asset_id"] == vehicle["id"]
    duplicate = await client.post(
        "/inventory/locations",
        json={
            "name": "Duplicate engine",
            "location_type": "VEHICULO",
            "container_asset_id": vehicle["id"],
        },
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_location_type_requires_matching_container(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    client = authenticated_inventory_client
    for body in (
        {"name": "Invalid vehicle", "location_type": "VEHICULO"},
        {
            "name": "Invalid depot",
            "location_type": "FISICA",
            "container_asset_id": 1,
        },
        {"name": "Invalid type", "location_type": "OTHER"},
    ):
        response = await client.post("/inventory/locations", json=body)
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_location_listing_and_missing_id(
    inventory_session: AsyncSession, authenticated_inventory_client: AsyncClient
) -> None:
    client = authenticated_inventory_client
    assert (await client.get("/inventory/locations")).json() == []
    first = (
        await client.post(
            "/inventory/locations",
            json={"name": "Depot A", "location_type": "FISICA"},
        )
    ).json()
    second = (
        await client.post(
            "/inventory/locations",
            json={"name": "Depot B", "location_type": "FISICA"},
        )
    ).json()
    listing = await client.get("/inventory/locations")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [first["id"], second["id"]]
    assert (
        await client.get(f"/inventory/locations/{second['id'] + 1}")
    ).status_code == 404


@pytest.mark.asyncio
async def test_asset_rejects_missing_or_inactive_location(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    missing_location_id = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM ubicaciones")
        )
    )
    client = authenticated_inventory_client
    missing = await client.post(
        "/inventory/assets",
        json={
            "internal_code": f"LOC-{uuid4().hex[:20]}",
            "name": "Hose",
            "category_id": category_id,
            "location_id": missing_location_id,
        },
    )
    assert missing.status_code == 409

    inactive = (
        await client.post(
            "/inventory/locations",
            json={
                "name": "Closed depot",
                "location_type": "FISICA",
                "active": False,
            },
        )
    ).json()
    rejected = await client.post(
        "/inventory/assets",
        json={
            "internal_code": f"LOC-{uuid4().hex[:20]}",
            "name": "Hose",
            "category_id": category_id,
            "location_id": inactive["id"],
        },
    )
    assert rejected.status_code == 409


@pytest.mark.asyncio
async def test_database_rejects_vehicle_containment_cycle(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    client = authenticated_inventory_client
    first_asset = await create_asset(client, category_id)
    first_location = (
        await client.post(
            "/inventory/locations",
            json={
                "name": "Vehicle A",
                "location_type": "VEHICULO",
                "container_asset_id": first_asset["id"],
            },
        )
    ).json()
    second_asset = await create_asset(
        client, category_id, location_id=first_location["id"]
    )
    second_location = (
        await client.post(
            "/inventory/locations",
            json={
                "name": "Vehicle B",
                "location_type": "VEHICULO",
                "container_asset_id": second_asset["id"],
            },
        )
    ).json()

    with pytest.raises(IntegrityError):
        await inventory_session.execute(
            update(Asset)
            .where(Asset.id == first_asset["id"])
            .values(ubicacion_id=second_location["id"])
        )
        await inventory_session.commit()
    await inventory_session.rollback()


@pytest.mark.asyncio
async def test_database_rejects_direct_self_containment(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    client = authenticated_inventory_client
    asset = await create_asset(client, category_id)
    location = (
        await client.post(
            "/inventory/locations",
            json={
                "name": "Vehicle A",
                "location_type": "VEHICULO",
                "container_asset_id": asset["id"],
            },
        )
    ).json()

    with pytest.raises(IntegrityError):
        await inventory_session.execute(
            update(Asset)
            .where(Asset.id == asset["id"])
            .values(ubicacion_id=location["id"])
        )
        await inventory_session.commit()
    await inventory_session.rollback()


@pytest.mark.asyncio
async def test_deleting_location_clears_asset_reference(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    client = authenticated_inventory_client
    location = (
        await client.post(
            "/inventory/locations",
            json={"name": "Temporary depot", "location_type": "FISICA"},
        )
    ).json()
    asset = await create_asset(client, category_id, location_id=location["id"])

    await inventory_session.execute(
        delete(Location).where(Location.id == location["id"])
    )
    await inventory_session.commit()
    stored = await inventory_session.get(Asset, asset["id"])
    assert stored is not None
    await inventory_session.refresh(stored)
    assert stored.ubicacion_id is None


@pytest.mark.asyncio
async def test_transfer_updates_location_and_records_history(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    user = await create_test_user(inventory_session)
    client = authenticated_inventory_client
    origin = (
        await client.post(
            "/inventory/locations",
            json={"name": "Depot A", "location_type": "FISICA"},
        )
    ).json()
    destination = (
        await client.post(
            "/inventory/locations",
            json={"name": "Engine bay", "location_type": "FISICA"},
        )
    ).json()
    asset = await create_asset(client, category_id, location_id=origin["id"])
    client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )
    response = await client.post(
        f"/inventory/assets/{asset['id']}/transfers",
        json={"destination_location_id": destination["id"], "reason": "Dispatch"},
    )
    assert response.status_code == 201, response.text
    movement = response.json()
    assert movement["asset_id"] == asset["id"]
    assert movement["user_id"] == user.id
    assert movement["movement_type"] == "TRASLADO"
    assert movement["origin_location_id"] == origin["id"]
    assert movement["destination_location_id"] == destination["id"]
    assert movement["reason"] == "Dispatch"
    assert movement["occurred_at"]
    assert (await client.get(f"/inventory/assets/{asset['id']}")).json()[
        "location_id"
    ] == destination["id"]
    history = await client.get(f"/inventory/assets/{asset['id']}/transfers")
    assert history.status_code == 200
    assert history.json() == [movement]


@pytest.mark.asyncio
async def test_transfer_rejects_unauthenticated_request(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    client = authenticated_inventory_client
    destination = (
        await client.post(
            "/inventory/locations",
            json={"name": "Depot B", "location_type": "FISICA"},
        )
    ).json()
    asset = await create_asset(client, category_id)
    token = client.cookies.get(ACCESS_TOKEN_COOKIE)
    assert token is not None
    client.cookies.delete(ACCESS_TOKEN_COOKIE)
    response = await client.post(
        f"/inventory/assets/{asset['id']}/transfers",
        json={"destination_location_id": destination["id"]},
    )
    assert response.status_code == 401
    client.cookies.set(ACCESS_TOKEN_COOKIE, token)
    assert (await client.get(f"/inventory/assets/{asset['id']}")).json()[
        "location_id"
    ] is None


@pytest.mark.asyncio
async def test_repeated_transfers_keep_ordered_origin_and_destination(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    user = await create_test_user(inventory_session)
    client = authenticated_inventory_client
    locations = []
    for name in ("Depot A", "Depot B", "Depot C"):
        response = await client.post(
            "/inventory/locations",
            json={"name": name, "location_type": "FISICA"},
        )
        locations.append(response.json()["id"])
    asset = await create_asset(client, category_id, location_id=locations[0])
    client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )
    for destination in locations[1:]:
        response = await client.post(
            f"/inventory/assets/{asset['id']}/transfers",
            json={"destination_location_id": destination},
        )
        assert response.status_code == 201, response.text
    history = (await client.get(f"/inventory/assets/{asset['id']}/transfers")).json()
    assert [
        (entry["origin_location_id"], entry["destination_location_id"])
        for entry in history
    ] == [
        (locations[0], locations[1]),
        (locations[1], locations[2]),
    ]
    assert (await client.get(f"/inventory/assets/{asset['id']}")).json()[
        "location_id"
    ] == locations[2]


@pytest.mark.asyncio
async def test_failed_transfers_do_not_change_asset_or_history(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    user = await create_test_user(inventory_session)
    client = authenticated_inventory_client
    origin = (
        await client.post(
            "/inventory/locations",
            json={"name": "Depot A", "location_type": "FISICA"},
        )
    ).json()["id"]
    inactive = (
        await client.post(
            "/inventory/locations",
            json={"name": "Closed", "location_type": "FISICA", "active": False},
        )
    ).json()["id"]
    asset = await create_asset(client, category_id, location_id=origin)
    client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )
    for destination, expected in ((origin, 409), (inactive, 409), (-1, 422)):
        response = await client.post(
            f"/inventory/assets/{asset['id']}/transfers",
            json={"destination_location_id": destination},
        )
        assert response.status_code == expected, response.text
    missing_id = int(
        await inventory_session.scalar(
            text("SELECT COALESCE(MAX(id), 0) + 1 FROM bienes")
        )
    )
    missing_asset = await client.post(
        f"/inventory/assets/{missing_id}/transfers",
        json={"destination_location_id": origin},
    )
    assert missing_asset.status_code == 404
    assert (await client.get(f"/inventory/assets/{asset['id']}")).json()[
        "location_id"
    ] == origin
    assert (await client.get(f"/inventory/assets/{asset['id']}/transfers")).json() == []


@pytest.mark.asyncio
async def test_cycle_rejection_rolls_back_transfer_and_history(
    inventory_session: AsyncSession,
    authenticated_inventory_client: AsyncClient,
) -> None:
    category_id = await create_category(inventory_session)
    user = await create_test_user(inventory_session)
    client = authenticated_inventory_client
    vehicle = await create_asset(client, category_id)
    vehicle_location = (
        await client.post(
            "/inventory/locations",
            json={
                "name": "Engine",
                "location_type": "VEHICULO",
                "container_asset_id": vehicle["id"],
            },
        )
    ).json()
    client.cookies.set(
        ACCESS_TOKEN_COOKIE, create_access_token(user.id, get_settings().secret_key)
    )
    response = await client.post(
        f"/inventory/assets/{vehicle['id']}/transfers",
        json={"destination_location_id": vehicle_location["id"]},
    )
    assert response.status_code == 409, response.text
    assert (await client.get(f"/inventory/assets/{vehicle['id']}")).json()[
        "location_id"
    ] is None
    assert (
        await client.get(f"/inventory/assets/{vehicle['id']}/transfers")
    ).json() == []
