# Odoo 18: este módulo ya no aporta lógica Python. El override v16 sobre
# `bank.rec.widget._process_todo_command` se eliminó porque ese dispatcher de
# comandos por string fue removido en v18; las acciones del frontend ahora
# llaman directamente a métodos granulares `_js_action_add_new_aml(aml_id)` y
# `_js_action_remove_new_aml(aml_id)` ya provistos por upstream.
