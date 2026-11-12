# language: es
# Criterios de aceptacion: Carrito
# Nota para el agente QA: estos criterios describen COMPORTAMIENTO esperado.
# La aplicacion se encuentra en BASE_URL (variable de entorno). Debes descubrir
# tu propio camino hasta las pantallas relevantes.
@ui @carrito
Característica: Carrito de compras
  Como comprador del sitio
  Quiero gestionar los productos que agrego al carrito
  Para revisar y confirmar mi compra con total precision

  Antecedentes:
    Dado que el catalogo tiene productos con precios en COP
    Y el IVA aplicable es 19%

  @criterio-cart-01
  Escenario: Agregar un producto desde el catalogo
    Dado que estoy en la pagina principal
    Cuando navego al catalogo de productos
    Y agrego el producto "Teclado Mecanico K7" al carrito
    Entonces el carrito debe contener 1 linea con cantidad 1
    Y el subtotal de esa linea debe ser 45990.00

  @criterio-cart-02
  Escenario: El total del carrito incluye IVA y se redondea a 2 decimales
    Dado que agregue 3 unidades del producto "Teclado Mecanico K7" (45990 c/u)
    Cuando abro mi carrito
    Entonces el subtotal debe ser 137970.00
    Y el IVA debe ser 26214.30
    Y el total debe ser 164184.30

  @criterio-cart-03
  Escenario: Cambiar la cantidad actualiza el total
    Dado que tengo 1 unidad del producto "Mouse Inalambrico M2" (28990 c/u) en el carrito
    Cuando cambio la cantidad a 2
    Entonces el subtotal debe ser 57980.00
    Y el total debe ser 69002.20

  @criterio-cart-04
  Escenario: La cantidad minima por linea es 1
    Dado que tengo un producto en el carrito
    Cuando intento poner la cantidad de la linea en 0
    Entonces el sistema no debe aceptar cantidades menores a 1
    Y el total nunca debe ser negativo o nulo por causa de la cantidad

  @criterio-cart-05
  Escenario: Eliminar una linea del carrito
    Dado que tengo 2 productos en el carrito
    Cuando elimino uno de ellos
    Entonces el carrito debe contener solo el producto restante
    Y los totales deben recalcularse

  @criterio-cart-06
  Escenario: Carrito vacio muestra estado vacio
    Dado que no agregue ningun producto
    Cuando abro el carrito
    Entonces debo ver un mensaje de carrito vacio
    Y el total no debe mostrarse o debe ser 0.00
