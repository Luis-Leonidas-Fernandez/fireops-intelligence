# Acceso con Google en el entorno local

El navegador inicia el flujo de Google, pero **FastAPI** intercambia el código y verifica la identidad. La aplicación conserva su sesión local de 30 minutos en una cookie HttpOnly; no guarda tokens de Google.

## Preparación por integrante

1. Sincronizar el repositorio e instalar `requirements.txt` en `.venv` (incluye `google-auth[requests]`).
2. Crear o comprobar la base local `fireassets_test` y verificar que `DATABASE_URL` de `.env.test` apunta exactamente a ella.
3. Configurar en `.env.test` —y en `.env` si también se utiliza ese entorno— los valores **privados** del mismo cliente OAuth de tipo *Aplicación web*:

   ```env
   GOOGLE_CLIENT_ID=<client-id-del-cliente-web>
   GOOGLE_CLIENT_SECRET=<secreto-del-cliente-web>
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
   ```

   El URI debe coincidir exactamente con el **URI de redireccionamiento autorizado** de Google Cloud. Si la pantalla de consentimiento está en modo de prueba, agregar las cuentas del equipo como usuarios de prueba. No copiar secretos reales a `.env.example`, Git, mensajes ni capturas.
4. Aplicar todas las revisiones pendientes de Alembic, incluida `d8b6e2f1940a` para el nombre opcional, **solo a `fireassets_test`**. En macOS:

   ```bash
   ENV_FILE=.env.test ./.venv/bin/python -m alembic upgrade head
   ./scripts/test-up.sh
   ```

   En Windows PowerShell:

   ```powershell
   $previousEnvFile = $env:ENV_FILE
   try {
       $env:ENV_FILE = ".env.test"
       & .\.venv\Scripts\python.exe -m alembic upgrade head
   }
   finally {
       if ($null -eq $previousEnvFile) {
           Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue
       } else {
           $env:ENV_FILE = $previousEnvFile
       }
   }
   .\scripts\test-up.ps1
   ```

   Verificar el nombre de la base en `.env.test` **antes** de ejecutar Alembic. El script de inicio controla `fireassets_test`, pero el comando Alembic no lo hace por sí mismo.

## Prueba manual

Abrir `http://127.0.0.1:8000/iniciar-sesion` y seleccionar el icono de Google. Una cuenta Google nueva con correo verificado crea un usuario local; los ingresos posteriores usan la misma cuenta. Si ya existe una cuenta con contraseña y ese correo, iniciar sesión con contraseña y elegir **Vincular Google** en el menú de perfil del dashboard. El correo Google debe coincidir; nunca se vincula automáticamente por correo.

Comprobar también cancelación de Google, cierre de sesión y retorno a `/iniciar-sesion`. Si faltan las variables, el botón muestra un mensaje controlado y el acceso con contraseña continúa funcionando. Los tokens de Google no se exponen a JavaScript ni se almacenan en PostgreSQL.

El flujo solicita `openid profile email` para obtener el nombre de perfil cuando Google lo proporciona. Ese nombre se guarda en `usuarios.display_name` y aparece en el app bar mediante `GET /auth/me`; si no está disponible, se muestra el correo. Una cuenta Google creada antes de esta revisión puede mostrar el correo hasta volver a ingresar con Google. El nombre ya guardado no se reemplaza automáticamente si cambia en Google.

## Diagnóstico seguro en la terminal

El servidor escribe eventos JSON `google_oauth` con un `attempt_id` aleatorio. Buscá ese identificador en las líneas de `start`, `token_exchange`, `identity` y `callback` para seguir **un mismo intento**, incluso cuando varios integrantes prueben a la vez. Ejemplo ficticio:

```text
{"event":"google_oauth","attempt_id":"0123456789abcdef01234567","stage":"token_exchange","outcome":"failed","reason":"provider_http_error","http_status":400}
```

- `start/rejected`: falta configuración o sesión local para vincular.
- `callback/rejected`: cookie ausente/inválida, `state` incorrecto, cancelación o falta del código.
- `token_exchange/failed`: Google rechazó el intercambio, hubo un problema de red o faltó el ID token. Un HTTP 400 **no identifica por sí solo** cuál valor de configuración es incorrecto; verificá Client ID, Client Secret y URI de retorno sin copiarlos al chat.
- `identity/rejected` o `identity/failed`: faltó un claim obligatorio, falló el `nonce` o no se pudo verificar el token.
- `account/failed`: conflicto de cuenta, vinculación no permitida o pérdida de la sesión local. `account/succeeded` confirma la cuenta local.
- `callback/failed`: el error controlado final. `callback/succeeded` confirma que se emitió la sesión local o se completó la vinculación.

Los eventos no incluyen correo, usuario, código OAuth, tokens, `state`, `nonce`, respuesta del proveedor ni claves. El motor SQLAlchemy tampoco imprime consultas ni parámetros en la terminal: esos parámetros pueden contener correos y hashes. No pegues valores de `.env` ni trazas que puedan contener credenciales. Si el navegador muestra un error genérico, conservá solamente los eventos `google_oauth` del mismo `attempt_id` para diagnosticarlo.

Los scripts `test-up.sh` y `test-up.ps1` arrancan Uvicorn con `--no-access-log`: esto mantiene la terminal limpia de ruido HTTP. Además, la aplicación cuenta con un filtro interno (`OAuthCallbackAccessLogFilter`) en `uvicorn.access` que elimina completamente la query string de `/auth/google/callback` antes de que cualquier registro sea formateado o emitido, preservando método, ruta, status y tiempos de respuesta. De este modo, incluso si Uvicorn se inicia en producción con access logs habilitados (sin `--no-access-log`), los parámetros temporales de autenticación (`code`, `state`) nunca se imprimirán en los logs del proceso.

## Seguridad en infraestructura y proxies perimetrales (Nginx / ALB / CDN)

> [!WARNING]
> La protección del filtro de logging en Python cubre **exclusivamente** el proceso local de Uvicorn/FastAPI. **No protege automáticamente** reverse proxies (Nginx, Caddy, Traefik), balanceadores de carga en la nube (AWS ALB, GCP Load Balancer), redes de distribución (Cloudflare) ni colectores de observabilidad externos si estos registran la URL entrante completa en el perímetro.

Por defecto, la directiva `combined` de Nginx registra la variable `$request` (`$request_method $request_uri $server_protocol`), donde `$request_uri` contiene la query string completa con el código de autorización. Asimismo, peticiones posteriores al callback podrían capturar la URL con código en el encabezado `$http_referer`.

Para evitar la persistencia de credenciales en los logs de acceso perimetrales de Nginx sin perder observabilidad operativa, se debe emplear un formato de log sanitizado que:
1. Enmascare la query string de `/auth/google/callback` en la ruta de solicitud.
2. Enmascare la query string si `/auth/google/callback` aparece en el encabezado `Referer`.
3. Evite estrictamente variables que contengan parámetros sin filtrar, como `$request`, `$args` o `$query_string`.

### Configuración recomendada para Nginx

```nginx
# 1. Enmascarar la query string de /auth/google/callback en la solicitud
map $uri $sanitized_request_uri {
    /auth/google/callback  $uri;
    default                $request_uri;
}

# 2. Enmascarar la query string si el callback aparece como Referer en peticiones posteriores
map $http_referer $sanitized_http_referer {
    ~^(?<referer_base>https?://[^/?]+)?/auth/google/callback\?  "$referer_base/auth/google/callback";
    default                                                      $http_referer;
}

# 3. Formato seguro que no expone $request, $args ni $query_string
log_format safe_combined '$remote_addr - $remote_user [$time_local] '
                         '"$request_method $sanitized_request_uri $server_protocol" '
                         '$status $body_bytes_sent '
                         '"$sanitized_http_referer" "$http_user_agent"';

# 4. Aplicar el formato seguro al log de acceso del servidor
access_log /var/log/nginx/access.log safe_combined;
```

## Pruebas automatizadas

```bash
# macOS, desde la raíz
ENV_FILE=.env.test ./.venv/bin/python -m pytest -q tests/modules/auth
node --test
```

En Windows, establecer `ENV_FILE=.env.test` para el comando de pytest y quitar la variable después, como se muestra arriba. Los tests simulan Google: **no requieren credenciales reales ni conexión a Google**, pero sí PostgreSQL local y la migración aplicada a `fireassets_test`. La fixture rechaza cualquier otra base y revierte los datos de cada prueba.

> El registro público sigue habilitado temporalmente y los endpoints de inventario aún no exigen autorización. Este flujo no convierte la aplicación en un sistema listo para producción; las invitaciones y la protección de la API son trabajos posteriores.
