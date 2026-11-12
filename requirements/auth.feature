# language: es
# Criterios de aceptacion: Autenticacion y cuenta
@ui @auth
Característica: Autenticación y cuenta
  Como usuario del sitio
  Quiero registrarme, ingresar y salir de forma segura
  Para que mi informacion este protegida

  Antecedentes:
    Dado que existe un usuario demo "sofia@demo.com" con contrasena "demo1234"

  @criterio-auth-01
  Escenario: Login con credenciales validas
    Cuando ingreso con sofia@demo.com / demo1234
    Entonces debo ver mi nombre en "Mi cuenta"

  @criterio-auth-02
  Escenario: Login con credenciales invalidas
    Cuando ingreso con una contrasena incorrecta
    Entonces debo ver un mensaje de credenciales invalidas
    Y no debo quedar autenticado

  @criterio-auth-03
  Escenario: Registro de nuevo usuario
    Cuando me registro con un email valido y contrasena de 8 caracteres
    Entonces debo quedar autenticado automaticamente

  @criterio-auth-04
  Escenario: Contraseña demasiado corta
    Cuando intento registrarme con contrasena "123"
    Entonces debo ver un error indicando el minimo de 6 caracteres

  @criterio-auth-05
  Escenario: El logout invalida el acceso a la cuenta
    Dado que estoy autenticado
    Cuando cierro sesion
    Y navego a "Mi cuenta"
    Entonces debo ser redirigido al login
    Y no debo ver informacion de la cuenta
