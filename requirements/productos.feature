# language: es
# Criterios de aceptacion: Catalogo de productos
@ui @productos
Característica: Catalogo de productos
  Como comprador del sitio
  Quiero buscar, filtrar y ordenar el catalogo
  Para encontrar el producto que necesito

  Antecedentes:
    Dado que el catalogo contiene 12 productos en 5 categorias
    Y el listado pagina 6 productos por pagina

  @criterio-cat-01
  Escenario: La busqueda cubre todo el catalogo
    Cuando busco "monitor" en el catalogo
    Entonces debo ver exactamente los productos "Monitor 24\" IPS" y "Monitor 27\" Curvo"
    Y ninguno debe quedar excluido por estar en otra pagina

  @criterio-cat-02
  Escenario: Ordenar por precio de menor a mayor es numerico
    Cuando ordeno el catalogo por "Precio (menor a mayor)"
    Entonces el primer producto debe ser el mas barato de todo el catalogo (12990)
    Y los precios deben mostrarse en orden estrictamente creciente

  @criterio-cat-03
  Escenario: Filtrar por categoria
    Cuando filtro la categoria "Audio"
    Entonces solo debo ver productos de esa categoria
    Y el contador de resultados debe coincidir con los visibles

  @criterio-cat-04
  Escenario: La paginacion refleja el contenido real
    Cuando navego a la ultima pagina anunciada por la paginacion
    Entonces esa pagina debe tener productos
    Y no deben existir enlaces a paginas sin contenido

  @criterio-cat-05
  Escenario: Busqueda sin resultados
    Cuando busco un termino que no coincide con ningun producto
    Entonces debo ver un mensaje explicito de "sin resultados"

  @criterio-cat-06
  Escenario: Detalle de producto
    Cuando abro el detalle del producto "Teclado Mecanico K7"
    Entonces debo ver su precio 45990, la categoria y una forma de agregarlo al carrito
