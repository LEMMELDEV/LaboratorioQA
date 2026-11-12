# language: es
# Criterios de aceptacion: Inicio, contacto y navegacion global
@ui @global
Característica: Navegación global, newsletter y contacto
  Como visitante del sitio
  Quiero navegar las secciones y suscribirme a novedades
  Para conocer la tienda y contactarme

  @criterio-nav-01
  Escenario: Navegacion principal
    Cuando recorro los enlaces del menu principal
    Entonces las secciones Inicio, Productos, Servicios y Contacto deben cargar correctamente

  @criterio-nav-02
  Escenario: Suscripcion a newsletter persiste
    Cuando me suscribo con el email "nuevo@ejemplo.com"
    Entonces debo ver una confirmacion de suscripcion
    Y mi email debe quedar registrado en el sistema

  @criterio-nav-03
  Escenario: Formulario de contacto con validaciones
    Cuando envio el formulario de contacto vacio
    Entonces debo ver errores en nombre, email y mensaje
    Cuando lo envio completo
    Entonces debo ver una confirmacion de envio

  @criterio-nav-04
  Escenario: Todos los enlaces del sitio responden
    Cuando reviso los enlaces de pie de pagina (footer)
    Entonces ningun enlace debe responder 404

  @criterio-nav-05
  Escenario: Preguntas frecuentes
    Cuando abro la seccion de contacto
    Entonces debo ver al menos 3 preguntas frecuentes desplegables
