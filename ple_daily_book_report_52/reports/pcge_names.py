# -*- coding: utf-8 -*-
"""Nombres abreviados del PCGE (2019) para la cabecera de columnas del
Formato 5.2 matricial.

Se usan cuando la compania no tiene un account.group con el prefijo de la
columna. Orden de resolucion (ver _resolve_column_names en el modelo):
  1. account.group de la compania con ese prefijo
  2. esta tabla (prefijo exacto; si termina en 0, tambien sin el 0 final:
     1220 -> 122, 6760 -> 676)
  3. nombre de la primera cuenta de la compania con ese prefijo

Los nombres se imprimen en dos lineas bajo el codigo, por eso van
abreviados (~32 caracteres como maximo). El elemento 9 es de uso libre de
cada empresa: los nombres incluidos son los del modelo de referencia y se
pueden ajustar.
"""

PCGE_GROUP_NAMES = {
    # ------------------------------------------------------------------
    # Elemento 1 - Activo disponible y exigible
    # ------------------------------------------------------------------
    '10': 'Efectivo y equivalentes',
    '101': 'Caja',
    '102': 'Fondos fijos',
    '103': 'Efectivo en transito',
    '104': 'Ctas. corrientes en inst. financieras',
    '1041': 'Ctas. corrientes operativas',
    '1042': 'Ctas. corrientes fines especificos',
    '105': 'Otros equivalentes de efectivo',
    '106': 'Depositos en inst. financieras',
    '1061': 'Depositos de ahorro',
    '1062': 'Depositos a plazo',
    '107': 'Fondos sujetos a restriccion',
    '12': 'CxC comerciales terceros',
    '121': 'Facturas por cobrar',
    '1211': 'Facturas por cobrar no emitidas',
    '1212': 'Facturas por cobrar emitidas en cartera',
    '1213': 'Facturas por cobrar en cobranza',
    '1214': 'Facturas por cobrar en descuento',
    '122': 'Anticipos de clientes',
    '123': 'Letras por cobrar',
    '1231': 'Letras por cobrar en cartera',
    '1232': 'Letras por cobrar en cobranza',
    '1233': 'Letras por cobrar en descuento',
    '13': 'CxC comerciales relacionadas',
    '131': 'Facturas por cobrar relacionadas',
    '132': 'Anticipos recibidos relacionadas',
    '133': 'Letras por cobrar relacionadas',
    '14': 'CxC personal, accionistas y ger.',
    '141': 'CxC al personal',
    '1411': 'Prestamos al personal',
    '1412': 'Adelanto de remuneraciones',
    '1413': 'Entregas a rendir cuenta',
    '142': 'CxC a accionistas',
    '143': 'CxC a directores',
    '144': 'CxC a gerentes',
    '16': 'CxC diversas terceros',
    '161': 'Prestamos por cobrar',
    '162': 'Reclamaciones a terceros',
    '1621': 'Reclamos compañias aseguradoras',
    '1622': 'Reclamos transportadoras',
    '1623': 'Reclamos servicios publicos',
    '1624': 'Reclamos tributos',
    '1629': 'Otras reclamaciones',
    '163': 'Intereses, regalias y dividendos',
    '164': 'Depositos otorgados en garantia',
    '165': 'Venta de activo inmovilizado',
    '168': 'Otras CxC diversas',
    '1681': 'Entregas a rendir cuenta terceros',
    '1682': 'Otras CxC diversas',
    '17': 'CxC diversas relacionadas',
    '18': 'Servicios contratados por anticip.',
    '181': 'Costos financieros por anticipado',
    '182': 'Seguros pagados por anticipado',
    '183': 'Alquileres pagados por anticipado',
    '185': 'Mantenimiento por anticipado',
    '189': 'Otros gastos por anticipado',
    '19': 'Estim. cobranza dudosa',
    '191': 'Estim. cobranza dudosa comerciales',
    '196': 'Estim. cobranza dudosa diversas',

    # ------------------------------------------------------------------
    # Elemento 2 - Activo realizable
    # ------------------------------------------------------------------
    '20': 'Mercaderias',
    '201': 'Mercaderias manufacturadas',
    '2011': 'Mercaderias manufacturadas',
    '21': 'Productos terminados',
    '22': 'Subproductos, desechos',
    '23': 'Productos en proceso',
    '24': 'Materias primas',
    '25': 'Mat. auxiliares, sumin. y repuestos',
    '251': 'Materiales auxiliares',
    '252': 'Suministros',
    '253': 'Repuestos',
    '26': 'Envases y embalajes',
    '28': 'Existencias por recibir',
    '29': 'Desvalorizacion de existencias',

    # ------------------------------------------------------------------
    # Elemento 3 - Activo inmovilizado
    # ------------------------------------------------------------------
    '30': 'Inversiones mobiliarias',
    '31': 'Inversiones inmobiliarias',
    '32': 'Activos por derecho de uso',
    '33': 'Propiedades, planta y equipo',
    '331': 'Terrenos',
    '332': 'Edificaciones',
    '333': 'Maquinarias y equipos',
    '334': 'Unidades de transporte',
    '3341': 'Vehiculos motorizados',
    '3342': 'Vehiculos no motorizados',
    '335': 'Muebles y enseres',
    '3351': 'Muebles',
    '3352': 'Enseres',
    '336': 'Equipos diversos',
    '3361': 'Equipo procesamiento informacion',
    '3369': 'Otros equipos',
    '337': 'Herramientas y unid. reemplazo',
    '338': 'Unidades por recibir',
    '339': 'Obras en curso',
    '34': 'Intangibles',
    '343': 'Programas de computadora',
    '35': 'Activos biologicos',
    '36': 'Desvalorizacion activo inmovil.',
    '37': 'Activo diferido',
    '38': 'Otros activos',
    '39': 'Deprec., amortiz. y agot. acum.',
    '3952': 'Deprec. acum. PPE costo',

    # ------------------------------------------------------------------
    # Elemento 4 - Pasivo
    # ------------------------------------------------------------------
    '40': 'Tributos y aportes por pagar',
    '401': 'Gobierno central',
    '4011': 'IGV',
    '4015': 'Derechos aduaneros',
    '4017': 'Impuesto a la renta',
    '4018': 'Otros impuestos',
    '403': 'Instituciones publicas',
    '4031': 'EsSalud',
    '4032': 'ONP',
    '405': 'Gobiernos regionales',
    '406': 'Gobiernos locales',
    '407': 'AFP',
    '409': 'Otros costos administrativos',
    '41': 'Remuneraciones por pagar',
    '411': 'Remuneraciones por pagar',
    '4111': 'Sueldos y salarios por pagar',
    '4114': 'Gratificaciones por pagar',
    '4115': 'Vacaciones por pagar',
    '413': 'Participaciones por pagar',
    '415': 'Beneficios sociales por pagar',
    '4151': 'CTS por pagar',
    '419': 'Otras remuneraciones por pagar',
    '42': 'CxP comerciales terceros',
    '421': 'Facturas por pagar',
    '4211': 'Facturas por pagar no emitidas',
    '4212': 'Facturas por pagar emitidas',
    '422': 'Anticipos a proveedores',
    '423': 'Letras por pagar',
    '424': 'Honorarios por pagar',
    '43': 'CxP comerciales relacionadas',
    '44': 'CxP accionistas, direct. y ger.',
    '441': 'CxP accionistas',
    '4411': 'Accionistas prestamos',
    '4412': 'Accionistas dividendos',
    '442': 'CxP directores',
    '443': 'CxP gerentes',
    '45': 'Obligaciones financieras',
    '451': 'Prestamos inst. financieras',
    '4511': 'Prestamos inst. financieras',
    '4512': 'Prestamos otras entidades',
    '452': 'Arrendamiento financiero',
    '455': 'Costos de financiacion por pagar',
    '46': 'CxP diversas terceros',
    '461': 'Reclamaciones de terceros',
    '465': 'Pasivos por compra activo inmov.',
    '467': 'Depositos recibidos en garantia',
    '469': 'Otras CxP diversas',
    '47': 'CxP diversas relacionadas',
    '48': 'Provisiones',
    '49': 'Pasivo diferido',

    # ------------------------------------------------------------------
    # Elemento 5 - Patrimonio
    # ------------------------------------------------------------------
    '50': 'Capital',
    '501': 'Capital social',
    '5011': 'Capital acciones',
    '5012': 'Capital participaciones',
    '51': 'Acciones de inversion',
    '52': 'Capital adicional',
    '56': 'Resultados no realizados',
    '57': 'Excedente de revaluacion',
    '58': 'Reservas',
    '59': 'Resultados acumulados',
    '591': 'Utilidades no distribuidas',
    '5911': 'Utilidades acumuladas',
    '592': 'Perdidas acumuladas',
    '5921': 'Perdidas acumuladas',

    # ------------------------------------------------------------------
    # Elemento 6 - Gastos por naturaleza
    # ------------------------------------------------------------------
    '60': 'Compras',
    '601': 'Compras mercaderias',
    '6011': 'Mercaderias manufacturadas',
    '602': 'Compras materias primas',
    '603': 'Compras mat. auxil. y sumin.',
    '604': 'Compras envases y embalajes',
    '609': 'Costos vinculados con compras',
    '61': 'Variacion de inventarios',
    '611': 'Variacion mercaderias',
    '6111': 'Variacion mercaderias',
    '612': 'Variacion materias primas',
    '613': 'Variacion mat. auxil. y sumin.',
    '62': 'Gastos de personal',
    '621': 'Remuneraciones',
    '6211': 'Sueldos y salarios',
    '6214': 'Gratificaciones',
    '6215': 'Vacaciones',
    '622': 'Otras remuneraciones',
    '627': 'Seguridad y prevision social',
    '6271': 'Regimen prestaciones de salud',
    '629': 'Beneficios sociales',
    '6291': 'Compensacion tiempo servicios',
    '63': 'Servicios prestados por terceros',
    '631': 'Transporte, correos y viajes',
    '6311': 'Transporte',
    '6312': 'Correos',
    '6313': 'Alojamiento',
    '6314': 'Alimentacion',
    '6315': 'Otros gastos de viaje',
    '632': 'Asesoria y consultoria',
    '6321': 'Asesoria administrativa',
    '6322': 'Asesoria legal y tributaria',
    '6323': 'Asesoria auditoria y contable',
    '6324': 'Asesoria mercadotecnia',
    '633': 'Produccion encargada a terceros',
    '634': 'Mantenimiento y reparaciones',
    '635': 'Alquileres',
    '6352': 'Alquiler edificaciones',
    '6353': 'Alquiler maquinarias',
    '6354': 'Alquiler equipo de transporte',
    '636': 'Servicios basicos',
    '6361': 'Energia electrica',
    '6362': 'Gas',
    '6363': 'Agua',
    '6364': 'Telefono',
    '6365': 'Internet',
    '637': 'Publicidad y relac. publicas',
    '638': 'Servicios de contratistas',
    '639': 'Otros servicios de terceros',
    '6391': 'Gastos bancarios',
    '6392': 'Gastos de laboratorio',
    '64': 'Gastos por tributos',
    '641': 'Tributos gobierno central',
    '6412': 'ITF',
    '643': 'Tributos gobierno local',
    '6431': 'Impuesto predial',
    '6432': 'Arbitrios',
    '65': 'Otros gastos de gestion',
    '651': 'Seguros',
    '654': 'Licencias y derechos',
    '655': 'Costo neto enajenacion activos',
    '656': 'Suministros',
    '659': 'Otros gastos de gestion',
    '6591': 'Donaciones',
    '6592': 'Sanciones administrativas',
    '66': 'Perdida medicion valor razonable',
    '67': 'Gastos financieros',
    '671': 'Gastos en op. de endeudamiento',
    '673': 'Intereses por prestamos',
    '676': 'Diferencia de cambio',
    '679': 'Otros gastos financieros',
    '68': 'Valuacion, deterioro y provisiones',
    '681': 'Depreciacion',
    '682': 'Amortizacion de intangibles',
    '684': 'Valuacion de activos',
    '686': 'Provisiones',
    '69': 'Costo de ventas',

    # ------------------------------------------------------------------
    # Elemento 7 - Ingresos
    # ------------------------------------------------------------------
    '70': 'Ventas',
    '701': 'Ventas mercaderias',
    '7011': 'Mercaderias manufacturadas',
    '702': 'Ventas productos terminados',
    '704': 'Prestacion de servicios',
    '7041': 'Servicios terceros',
    '7042': 'Servicios relacionadas',
    '709': 'Devoluciones sobre ventas',
    '71': 'Variacion produccion almacenada',
    '72': 'Produccion activo inmovilizado',
    '73': 'Descuentos obtenidos',
    '74': 'Descuentos concedidos',
    '75': 'Otros ingresos de gestion',
    '754': 'Alquileres',
    '756': 'Enajenacion activos inmovilizados',
    '759': 'Otros ingresos de gestion',
    '7599': 'Otros ingresos de gestion',
    '76': 'Ganancia medicion valor razonable',
    '77': 'Ingresos financieros',
    '772': 'Rendimientos ganados',
    '773': 'Dividendos',
    '776': 'Diferencia de cambio',
    '779': 'Otros ingresos financieros',
    '78': 'Cargas cubiertas por provisiones',
    '79': 'Cargas imputables a costos y gastos',
    '791': 'Cargas imputables a ctas. costos',
    '792': 'Gastos financ. imputables existencias',

    # ------------------------------------------------------------------
    # Elemento 8 - Saldos intermediarios
    # ------------------------------------------------------------------
    '80': 'Margen comercial',
    '81': 'Produccion del ejercicio',
    '82': 'Valor agregado',
    '83': 'Excedente bruto de explotacion',
    '84': 'Resultado de explotacion',
    '85': 'Resultado antes de participaciones',
    '87': 'Participaciones de trabajadores',
    '88': 'Impuesto a la renta',
    '89': 'Determinacion del resultado',

    # ------------------------------------------------------------------
    # Elemento 9 - Contabilidad analitica (uso libre; segun modelo)
    # ------------------------------------------------------------------
    '90': 'Costo de produccion',
    '91': 'Costos por distribuir',
    '9111': 'Costos de prod. gastos generales',
    '92': 'Costos de produccion',
    '94': 'Gastos administrativos',
    '95': 'Gastos de ventas',
    '9510': 'Gastos administrativos',
    '97': 'Gastos financieros',
    '9710': 'Gastos financ. diversos',
    '9761': 'Gastos por dif. de cambio',
}


def lookup_pcge_name(prefix):
    """Nombre de la tabla para un prefijo, o '' si no esta.

    Prueba el prefijo exacto y, si termina en ceros, el prefijo sin los
    ceros finales (las divisionarias '0' suelen ser la cuenta/subcuenta
    sin desagregar: 1220 -> 122, 7910 -> 791).
    """
    if not prefix:
        return ''
    if prefix in PCGE_GROUP_NAMES:
        return PCGE_GROUP_NAMES[prefix]
    trimmed = prefix
    while len(trimmed) > 2 and trimmed.endswith('0'):
        trimmed = trimmed[:-1]
        if trimmed in PCGE_GROUP_NAMES:
            return PCGE_GROUP_NAMES[trimmed]
    return ''