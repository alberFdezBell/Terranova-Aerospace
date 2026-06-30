# Terranova Aerospace Command Center

## Información general

**Nombre del proyecto:** Terranova Aerospace Command Center

**Objetivo:** proporcionar el punto de entrada principal de la aplicación para autenticar operadores, mostrar la carga inicial, presentar el centro de mando y abrir módulos externos.

**Descripción del sistema:** `principal.py` funciona como núcleo de navegación. El sistema arranca con autenticación local, ejecuta una pantalla de carga animada y muestra un panel principal desde el que se accede a los módulos operativos de la agencia ficticia Terranova Aerospace.

## Arquitectura

| Archivo o carpeta | Función |
| --- | --- |
| principal.py | Entrada principal, autenticación, pantallas animadas, centro de mando, visor del mapa orbital y lanzador de módulos. |
| icons/tas.png | Logo oficial de Terranova Aerospace. Debe usarse siempre que aparezca la identidad visual. |
| config/user.dat | Archivo local generado en el primer inicio con las credenciales protegidas del operador. |
| modules/ | Carpeta preparada para futuros módulos auxiliares. |
| AGENTS.md | Documentación técnica del sistema para futuros desarrolladores. |

### Flujo de ejecución

1. El usuario ejecuta `python principal.py`.
2. `principal.py` crea la aplicación PyQt6 y muestra la pantalla de autenticación.
3. Si no existe `config/user.dat`, se muestra el asistente "Configuración del operador".
4. Si ya existe un usuario, se muestra el usuario detectado y se solicita la contraseña.
5. Tras autenticar, aparece una pantalla de carga inicial con logo, spinner y mensajes dinámicos.
6. Se abre el centro de mando con las tarjetas de módulo.
7. Al elegir un módulo disponible, se muestra una transición animada. El mapa orbital se carga internamente en el mismo stacked widget; otros módulos futuros se ejecutarán como procesos independientes.

## Sistema de autenticación

La autenticación está implementada en la clase `AuthManager` dentro de `principal.py`.

En el primer inicio se solicitan:

- Nombre de usuario.
- Contraseña.

Los datos se guardan localmente en `config/user.dat`. La contraseña nunca se guarda en texto plano. El sistema utiliza:

- Algoritmo: `PBKDF2-HMAC-SHA256`.
- Salt aleatorio de 32 bytes.
- 240000 iteraciones.
- Comparación segura con `hmac.compare_digest`.

El archivo `user.dat` contiene JSON con el usuario, algoritmo, iteraciones, salt y hash codificados en Base64.

## Interfaz

La interfaz usa PyQt6 y mantiene una estética oscura, profesional y tecnológica:

- Fondo negro azulado.
- Paneles con transparencia ligera.
- Bordes suaves.
- Sombras discretas.
- Azul tecnológico suave como acento.
- Verde/cian para estados operativos.

Componentes principales:

- `LoginScreen`: pantalla de acceso y configuración inicial.
- `StartupLoadingScreen`: carga inicial con logo, spinner y mensajes rotativos.
- `CommandCenter`: cabecera corporativa y tarjetas de módulos.
- `ModuleTransitionScreen`: transición dinámica con logo, animación orbital y mensajes.
- `KSPRealTimeVisualizer`: visor 3D del mapa orbital de Kerbin integrado dentro de la ventana principal de la aplicación.
- `SpinnerWidget` y `OrbitalLoader`: widgets pintados con `QPainter` para animaciones fluidas.

El logo debe cargarse siempre desde `icons/tas.png`. No se deben crear logos alternativos ni sustituirlo por dibujos manuales.

## Módulos existentes

| Módulo | Archivo | Estado |
| --- | --- | --- |
| Mapa orbital | Integrado en `principal.py` | Disponible |
| Notas de prensa | - | Pendiente |
| Programación | - | Pendiente |
| Centro de mando | - | Pendiente |
| Personal | - | Pendiente |

## Guía para futuros desarrolladores

### Añadir nuevos módulos

1. Cree el script del nuevo módulo en la raíz del proyecto o dentro de `modules/`.
2. Abra `principal.py`.
3. Actualice el diccionario `MODULES`:

```python
MODULES = {
    "Mapa orbital": "internal",
    "Nuevo módulo": "modules/nuevo_modulo.py",
}
```

Si el valor es `None`, el centro de mando mostrará el módulo como pendiente y avisará: "Módulo no disponible actualmente".

### Añadir nuevos menús

Los menús se generan desde `MODULES`. Para agregar una tarjeta nueva basta con añadir una entrada al diccionario. `CommandCenter` creará automáticamente la tarjeta correspondiente.

### Modificar estilos

Los estilos visuales están centralizados en la función `build_stylesheet()` de `principal.py`. Ajuste colores, bordes, tipografía y estados hover desde esa función para mantener una apariencia coherente.

### Mantener la estructura

- Mantenga la autenticación en `AuthManager`.
- Mantenga las pantallas como clases independientes.
- No duplique estilos por pantalla si puede centralizarlos en `build_stylesheet()`.
- Use rutas relativas a `BASE_DIR` para que la aplicación funcione desde cualquier directorio de ejecución.
- Conserve `icons/tas.png` as única fuente del logo.
- Documente cualquier módulo nuevo en esta tabla y en el diccionario `MODULES`.
