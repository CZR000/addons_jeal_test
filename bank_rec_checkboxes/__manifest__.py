{
    'name': 'Bank Reconciliation - Checkboxes Sync',
    'version': '18.0.1.0.3',
    'category': 'Accounting',
    'summary': 'Enable checkboxes in Bank Reconciliation and sync them with reconciliation selection.',
    'description': """
Habilita la columna de selector (checkboxes) en la lista de
Journal Items dentro del widget de Bank Reconciliation y sincroniza
su estado visual con la selección real de la reconciliación.

Odoo 18: el widget de Bank Reconciliation fue reescrito completamente
del modelo `bank_rec_form_list` (widget jQuery) al componente Owl 2
`BankRecKanbanController` + `BankRecAmlsRenderer`. Este módulo
se actualiza con dos parches:

* `BankRecKanbanController.notebookAmlsListViewProps()` → activa
  `allowSelectors: true` (hardcoded `false` en upstream).
* `BankRecAmlsRenderer.toggleRecordSelection()` → enruta el click
  del checkbox a las acciones `env.config.actionAddNewAml(amlId)` /
  `actionRemoveNewAml(amlId)` y sincroniza el estado visual del
  checkbox con `bankRecRecordData.selected_aml_ids.currentIds`.

El override Python del v16 sobre `_process_todo_command` fue
eliminado: ese dispatcher de comandos por string ya no existe en
v18, sustituido por métodos `_js_action_*` granulares.
""",
    'depends': [
        'account_accountant',
        'web',
    ],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'bank_rec_checkboxes/static/src/js/bank_rec_allow_selectors_patch.js',
            'bank_rec_checkboxes/static/src/js/bank_rec_selectors_sync_patch.js',
        ],
    },
    'auto_install': True,
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
