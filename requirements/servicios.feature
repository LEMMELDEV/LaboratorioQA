# language: es
# Criterios de aceptacion: Servicios y cotizaciones
@ui @servicios
Característica: Servicios y cotizaciones
  Como cliente potencial
  Quiero solicitar cotizaciones de servicios tecnicos
  Para recibir una propuesta con codigo de seguimiento

  Antecedentes:
    Dado que existen 4 servicios publicados en el sitio

  @criterio-serv-01
  Escenario: Solicitud de cotizacion exitosa
    Cuando envio el formulario de cotizacion del servicio "Soporte remoto" con
      | nombre      | Luis Gomez              |
      | email       | luis.gomez@dominio.com  |
      | telefono    | 3001234567              |
      | presupuesto | 250000                  |
      | mensaje     | Mi PC no enciende       |
    Entonces debo recibir un codigo de seguimiento con formato "COT-" seguido de numeros
    Y el estado de la cotizacion debe ser "recibida"

  @criterio-serv-02
  Escenario: Emails validos con '+' deben aceptarse
    Cuando envio una cotizacion con el email "usuario+tag@dominio.com"
    Entonces la solicitud debe aceptarse

  @criterio-serv-03
  Escenario: Validaciones del formulario
    Cuando envio el formulario de cotizacion con telefono "123" y presupuesto "50000"
    Entonces debo ver mensajes de error para telefono (minimo 9 digitos)
    Y para presupuesto (minimo 100000)
    Y la cotizacion no debe crearse

  @criterio-serv-04
  Escenario: Los servicios listados son navegables
    Cuando navego a la seccion de servicios
    Entonces debo ver los 4 servicios con su precio y una accion para cotizar
