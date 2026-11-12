# language: es
# Criterios de aceptacion: Checkout
@ui @checkout
Característica: Checkout y ordenes
  Como comprador
  Quiero completar mis datos de envio y pago
  Para confirmar mi pedido

  Antecedentes:
    Dado que tengo productos en el carrito

  @criterio-chk-01
  Escenario: Compra exitosa genera numero de orden
    Cuando completo el checkout con
      | nombre    | Ana Torres              |
      | email     | ana@demo.com            |
      | direccion | Calle 10 #25-30         |
      | ciudad    | Bogota                  |
      | tarjeta   | 4111111111111111        |
    Entonces debo ver una confirmacion con un numero de orden con formato "ORD-"
    Y el carrito debe quedar vacio
    Y los totales de la orden deben coincidir con los del carrito

  @criterio-chk-02
  Escenario: La direccion de envio es obligatoria
    Cuando intento confirmar un pedido dejando la direccion vacia
    Entonces debo ver un error de campo obligatorio
    Y la orden no debe crearse

  @criterio-chk-03
  Escenario: La tarjeta debe tener 16 digitos
    Cuando intento confirmar un pedido con tarjeta "123"
    Entonces debo ver un error de formato en la tarjeta

  @criterio-chk-04
  Escenario: No se puede pagar con el carrito vacio
    Dado que el carrito esta vacio
    Cuando intento acceder al checkout
    Entonces debo ser llevado al carrito (o ver un mensaje equivalente)
