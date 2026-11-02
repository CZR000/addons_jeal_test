def migrate(cr, version):
    """Los bloques pasan de comercial / préstamos a "quién cobra": las ejecuciones
    calculadas con los bloques anteriores ya no se pueden leer con los nuevos y se
    borran (se regeneran con el asistente; las revisiones y los emparejamientos
    manuales se conservan). También se quita el filtro estático "Solo 2026" creado
    para la revisión en staging: lo reemplazan los filtros Año en curso / Mes en curso."""
    cr.execute("DELETE FROM ic_reconciliation_line")
    cr.execute("DELETE FROM ic_reconciliation_pair")
    cr.execute("DELETE FROM ic_reconciliation_run")
    cr.execute("DELETE FROM mail_activity WHERE res_model = 'ic.reconciliation.run'")
    cr.execute("DELETE FROM mail_message WHERE model = 'ic.reconciliation.run'")
    cr.execute("DELETE FROM ir_filters WHERE model_id = 'ic.reconciliation.line' AND name = 'Solo 2026'")
