# -*- coding: utf-8 -*-

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # ---------------------------------------------------------------------------- #
    #                           TODO - METODOS AUXILIARES                          #
    # ---------------------------------------------------------------------------- #
    def _get_partner_for_line(self, line):
        """
        Obtiene el socio vinculado a la línea contable.
        Si la empresa tiene activado `batch_payroll_move_lines`, se usa la configuración correspondiente.
        """
        company = self.company_id

        # Usar getattr para evitar AttributeError si el campo no existe
        batch_payroll_enabled = getattr(company, "batch_payroll_move_lines", False)

        if not batch_payroll_enabled and line.code == "NET":
            return self.employee_id.work_contact_id

        return line.partner_id

    def _get_analytic_distribution(self, line):
        """
        Determina la distribución analítica de la línea contable.

        - Si la regla salarial (`salary_rule_id`) tiene una cuenta analítica, se usa esta.
        - En caso contrario, se usa la cuenta analítica del contrato (`contract_id`).
        - Si no hay ninguna cuenta analítica, se devuelve un diccionario vacío.
        """
        analytic_account = (
            line.salary_rule_id.analytic_account_id
            or line.slip_id.contract_id.analytic_account_id
        )
        return {analytic_account.id: 100} if analytic_account else {}

    # ---------------------------------------------------------------------------- #
    #                      TODO - GENERACIÓN DE LÍNEA CONTABLE                     #
    # ---------------------------------------------------------------------------- #
    def _prepare_line_values(self, line, account_id, date, debit, credit):
        """
        Prepara los valores para la generación de la línea contable de nómina.

        - Determina el socio vinculado (`partner_id`).
        - Verifica si la cuenta contable permite distribución analítica (`enable_analytic_entries`).
        - Asigna una cuenta analítica solo si la cuenta tiene esta opción activada.
        - Retorna un diccionario con la estructura requerida por Odoo.
        """

        # Obtener el socio vinculado
        partner = self._get_partner_for_line(line)

        # Obtener la cuenta contable
        account = self.env["account.account"].browse(account_id)

        # Determinar si la cuenta permite distribución analítica
        allows_analytic_entries = account.enable_analytic_entries if account else False

        # Determinar la distribución analítica si la cuenta lo permite
        analytic_distribution = (
            self._get_analytic_distribution(line) if allows_analytic_entries else {}
        )

        return {
            "name": line.name,  # Descripción de la línea contable
            "partner_id": partner.id if partner else False,  # ID del socio vinculado
            "account_id": account_id,  # ID de la cuenta contable
            "journal_id": line.slip_id.struct_id.journal_id.id,  # Diario contable
            "date": date,  # Fecha de la operación
            "debit": debit,  # Monto del debe
            "credit": credit,  # Monto del haber
            "analytic_distribution": analytic_distribution,  # Distribución analítica si la cuenta lo permite
        }
