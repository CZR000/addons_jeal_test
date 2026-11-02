# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    advance_ids = fields.One2many(
        "l10n_pe.advance", "origin_move_id",
        string="Documentos generados", copy=False,
    )
    advance_application_ids = fields.One2many(
        "l10n_pe.advance.application", "move_id",
        string="Anticipos/revolventes aplicados", copy=False,
    )
    revolving_application_ids = fields.One2many(
        "l10n_pe.advance.application", "invoice_id",
        string="Revolventes aplicados", copy=False,
        domain=[("advance_type", "=", "revolving")],
    )
    l10n_pe_compensated_invoice_id = fields.Many2one(
        "account.move", string="Factura compensada", copy=False,
        readonly=True, index=True,
        help="Factura saldada por este asiento de compensacion de revolvente.",
    )
    advance_generated_count = fields.Integer(
        compute="_compute_advance_counts", string="N. documentos generados",
    )
    advance_application_count = fields.Integer(
        compute="_compute_advance_counts", string="N. aplicaciones",
    )
    advance_applied_base = fields.Monetary(
        compute="_compute_advance_counts", currency_field="currency_id",
        string="Base aplicada por anticipos",
    )
    revolving_application_count = fields.Integer(
        compute="_compute_advance_counts", string="N. revolventes aplicados",
    )
    compensation_revolving_count = fields.Integer(
        compute="_compute_advance_counts", string="N. revolventes compensados",
    )
    advance_available_amount = fields.Monetary(
        compute="_compute_advance_available", currency_field="currency_id",
        string="Anticipos disponibles",
    )
    revolving_available_amount = fields.Monetary(
        compute="_compute_advance_available", currency_field="currency_id",
        string="Revolvente disponible",
    )
    revolving_available_count = fields.Integer(
        compute="_compute_advance_available", string="N. depositos disponibles",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends(
        "advance_ids", "advance_application_ids.amount_base",
        "advance_application_ids.active", "revolving_application_ids",
    )
    def _compute_advance_counts(self):
        for move in self:
            m = move.sudo()
            move.advance_generated_count = len(m.advance_ids)
            apps = m.advance_application_ids.filtered("active")
            move.advance_application_count = len(apps)
            move.advance_applied_base = sum(apps.mapped("amount_base"))
            move.revolving_application_count = len(
                m.revolving_application_ids.filtered("active")
            )
            move.compensation_revolving_count = len(
                apps.filtered(
                    lambda a: a.application_type == "compensation"
                ).mapped("advance_id")
            )

    def _compute_advance_available(self):
        Advance = self.env["l10n_pe.advance"].sudo()
        for move in self:
            avail_adv = 0.0
            avail_rev = 0.0
            count_rev = 0
            partner = move.commercial_partner_id
            if partner and move.state == "draft" and move.move_type in (
                "out_invoice", "out_refund", "in_invoice", "in_refund"
            ):
                atype = (
                    "customer"
                    if move.move_type in ("out_invoice", "out_refund")
                    else "supplier"
                )
                advances = Advance.search([
                    ("partner_id", "=", partner.id),
                    ("advance_type", "=", atype),
                    ("state", "in", ("open", "partial")),
                    ("company_id", "=", move.company_id.id),
                ])
                avail_adv = sum(advances.mapped("amount_residual"))
            # Revolvente: solo facturas de cliente publicadas y en la misma
            # moneda del revolvente.
            if partner and move.state == "posted" and \
                    move.move_type == "out_invoice":
                revolvings = Advance.search([
                    ("partner_id", "=", partner.id),
                    ("advance_type", "=", "revolving"),
                    ("state", "in", ("open", "partial")),
                    ("company_id", "=", move.company_id.id),
                    ("currency_id", "=", move.currency_id.id),
                ])
                avail_rev = sum(revolvings.mapped("amount_residual"))
                count_rev = len(revolvings)
            move.advance_available_amount = avail_adv
            move.revolving_available_amount = avail_rev
            move.revolving_available_count = count_rev

    # ------------------------------------------------------------------
    # Posting hooks
    # ------------------------------------------------------------------
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted:
            move._l10n_pe_generate_advance_documents()
            move._l10n_pe_reconcile_advance_lines()
        return posted

    def write(self, vals):
        """La conciliacion bancaria no vuelve a publicar el asiento del
        extracto: reescribe sus lineas sobre el asiento ya publicado. Si en
        esa reescritura aparece un haber en la cuenta del revolvente, se crea
        el REV igual que al publicar un asiento manual."""
        res = super().write(vals)
        if "line_ids" in vals:
            for move in self.filtered(lambda m: m.state == "posted"):
                move._l10n_pe_generate_revolving_documents()
        return res

    def _l10n_pe_generate_advance_documents(self):
        """Al publicar: crea el documento de anticipo (producto de origen)
        o el revolvente (haber en la cuenta de control del revolvente).
        El mismo producto sirve para crear y para aplicar: las lineas de
        aplicacion se reconocen por estar enlazadas a un ANTC
        (l10n_pe_advance_id) y por tener importe negativo."""
        self.ensure_one()
        Advance = self.env["l10n_pe.advance"].sudo()
        Config = self.env["l10n_pe.advance.config"].sudo()

        # --- Anticipos de cliente / proveedor ---------------------------
        if self.move_type in ("out_invoice", "out_refund",
                              "in_invoice", "in_refund"):
            atype = (
                "customer"
                if self.move_type in ("out_invoice", "out_refund")
                else "supplier"
            )
            origin_lines = self.invoice_line_ids.filtered(
                lambda l: l.product_id.advance_role == "origin"
                and not l.l10n_pe_advance_id
                and self.currency_id.compare_amounts(l.price_subtotal, 0.0) > 0
            )
            for account in origin_lines.mapped("account_id"):
                # No duplicar si ya existe el documento para este origen/cuenta.
                if self.advance_ids.filtered(
                    lambda a: a.control_account_id == account
                    and a.advance_type == atype
                ):
                    continue
                config = Config._get_config(
                    atype, control_account=account,
                    currency=self.currency_id, company=self.company_id,
                )
                acc_lines = origin_lines.filtered(
                    lambda l: l.account_id == account
                )
                base = abs(sum(acc_lines.mapped("amount_currency")))
                if self.currency_id.is_zero(base):
                    continue
                total = sum(acc_lines.mapped("price_total"))
                subtotal = sum(acc_lines.mapped("price_subtotal"))
                Advance.create({
                    "advance_type": atype,
                    "partner_id": self.commercial_partner_id.id,
                    "currency_id": self.currency_id.id,
                    "company_id": self.company_id.id,
                    "date": self.invoice_date or self.date,
                    "config_id": config.id if config else False,
                    "control_account_id": account.id,
                    "origin_move_id": self.id,
                    "contract_ref": self.ref or self.invoice_origin or False,
                    "amount_base": base,
                    "amount_tax": total - subtotal,
                    "amount_total": total,
                })

        # --- Revolventes -------------------------------------------------
        self._l10n_pe_generate_revolving_documents()

    def _l10n_pe_generate_revolving_documents(self):
        """Un REV por cada apunte al HABER de la cuenta de control del
        revolvente, con socio, en la moneda de la configuracion y en uno de
        los diarios configurados. Cada REV queda enlazado a su apunte exacto
        (origin_line_id) y el apunte muestra su REV (l10n_pe_advance_id)."""
        self.ensure_one()
        # Los asientos de compensacion y de cierre son aplicaciones, no
        # depositos (ademas solo tienen apuntes al debe de la cuenta).
        if self.l10n_pe_compensated_invoice_id:
            return
        Advance = self.env["l10n_pe.advance"].sudo()
        Config = self.env["l10n_pe.advance.config"].sudo()
        rev_configs = Config.search([
            ("advance_type", "=", "revolving"),
            ("company_id", "=", self.company_id.id),
        ])
        for config in rev_configs:
            # Solo los diarios configurados disparan el revolvente.
            if config.revolving_journal_ids and \
                    self.journal_id not in config.revolving_journal_ids:
                continue
            credit_lines = self.line_ids.filtered(
                lambda l: l.account_id == config.control_account_id
                and l.partner_id
                and (l.currency_id or l.company_currency_id) == config.currency_id
                and config.currency_id.compare_amounts(l.amount_currency, 0.0) < 0
            )
            for line in credit_lines:
                if line.l10n_pe_advance_id or Advance.search_count([
                    ("origin_line_id", "=", line.id),
                ]):
                    continue
                deposit = abs(line.amount_currency)
                if config.currency_id.is_zero(deposit):
                    continue
                rev = Advance.create({
                    "advance_type": "revolving",
                    "partner_id": line.partner_id.commercial_partner_id.id,
                    "currency_id": config.currency_id.id,
                    "company_id": self.company_id.id,
                    "date": self.date,
                    "config_id": config.id,
                    "control_account_id": config.control_account_id.id,
                    "origin_move_id": self.id,
                    "origin_line_id": line.id,
                    "amount_base": deposit,
                    "amount_total": deposit,
                })
                line.sudo().write({"l10n_pe_advance_id": rev.id})

    def _l10n_pe_reconcile_advance_lines(self):
        """Concilia cada linea negativa de anticipo con el apunte de la cuenta
        de control del anticipo origen, y registra la aplicacion.
        Solo para facturas/NC: los asientos de compensacion (revolvente) y de
        cierre por redondeo registran su propia aplicacion desde el wizard."""
        self.ensure_one()
        if not self.is_invoice(include_receipts=True):
            return
        Application = self.env["l10n_pe.advance.application"].sudo()
        app_lines = self.line_ids.filtered(
            lambda l: l.l10n_pe_advance_id
            and l.account_id.reconcile
        )
        for line in app_lines:
            advance = line.l10n_pe_advance_id.sudo()
            # Evitar registrar dos veces (p. ej. post->draft->post).
            if Application.search_count([
                ("move_line_id", "=", line.id),
                ("advance_id", "=", advance.id),
            ]):
                continue
            origin_line = advance._get_open_control_line()
            full_reconcile = False
            if origin_line and not line.reconciled:
                (line + origin_line).sudo().reconcile()
                full_reconcile = line.full_reconcile_id.id
            app_type = (
                "credit_note"
                if self.move_type in ("out_refund", "in_refund")
                else "invoice"
            )
            Application.create({
                "advance_id": advance.id,
                "move_id": self.id,
                "invoice_id": self.id,
                "move_line_id": line.id,
                "date": self.invoice_date or self.date,
                "application_type": app_type,
                "amount_base": abs(line.amount_currency),
                "amount_total": abs(line.price_total),
                "amount_company_currency": abs(line.balance),
                "full_reconcile_id": full_reconcile,
            })

    # ------------------------------------------------------------------
    # Back to draft / reversal
    # ------------------------------------------------------------------
    def _l10n_pe_check_revolving_origin(self):
        """Un deposito cuyo REV ya tiene aplicaciones no puede pasarse a
        borrador ni revertirse: primero hay que revertir las compensaciones.
        Si el REV no tiene aplicaciones, se elimina (se vuelve a crear al
        publicar de nuevo el deposito)."""
        Advance = self.env["l10n_pe.advance"].sudo()
        for move in self:
            revs = Advance.search([
                ("origin_move_id", "=", move.id),
                ("advance_type", "=", "revolving"),
            ])
            used = revs.filtered(lambda r: r.application_ids)
            if used:
                raise UserError(_(
                    "El deposito %(move)s tiene revolventes con aplicaciones "
                    "(%(revs)s). Revierte primero los asientos de "
                    "compensacion.",
                    move=move.name, revs=", ".join(used.mapped("name")),
                ))
            if revs:
                revs.mapped("origin_line_id").sudo().write(
                    {"l10n_pe_advance_id": False}
                )
                revs.unlink()

    def _l10n_pe_release_applications(self):
        """Rompe las conciliaciones de las lineas de aplicacion de estos
        asientos y devuelve sus aplicaciones."""
        apps = self.env["l10n_pe.advance.application"].sudo().search([
            ("move_id", "in", self.ids),
        ])
        recon_lines = apps.mapped("move_line_id").filtered("reconciled")
        # Lineas de aplicacion (no los apuntes origen de un REV, que tambien
        # llevan l10n_pe_advance_id para mostrar su documento).
        recon_lines |= self.line_ids.filtered(
            lambda l: l.l10n_pe_advance_id and l.reconciled
            and l.l10n_pe_advance_id.origin_line_id != l
        )
        if recon_lines:
            recon_lines.sudo().remove_move_reconcile()
        return apps

    def button_draft(self):
        self._l10n_pe_check_revolving_origin()
        for move in self:
            # Romper solo las conciliaciones de las lineas de anticipo y
            # liberar el saldo, borrando las aplicaciones asociadas.
            apps = move._l10n_pe_release_applications()
            apps.unlink()
        return super().button_draft()

    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Al revertir un asiento de compensacion o de cierre, las
        aplicaciones se anulan (quedan inactivas, como historial) y los saldos
        de los revolventes/anticipos se liberan."""
        self._l10n_pe_check_revolving_origin()
        entries = self.filtered(
            lambda m: m.move_type == "entry" and m.sudo().advance_application_ids
        )
        apps = self.env["l10n_pe.advance.application"]
        if entries:
            apps = entries._l10n_pe_release_applications()
            # Tambien la conciliacion con la factura compensada.
            receivables = entries.line_ids.filtered(
                lambda l: l.account_id.account_type in (
                    "asset_receivable", "liability_payable"
                ) and (l.matched_debit_ids or l.matched_credit_ids)
            )
            if receivables:
                receivables.sudo().remove_move_reconcile()
        reversed_moves = super()._reverse_moves(
            default_values_list=default_values_list,
            # La reversion de una compensacion se cruza con el original.
            cancel=cancel or bool(entries),
        )
        if apps:
            apps.write({"active": False})
        return reversed_moves

    # ------------------------------------------------------------------
    # Actions (buttons)
    # ------------------------------------------------------------------
    def action_open_advance_apply_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicar anticipos"),
            "res_model": "l10n_pe.advance.apply.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_open_revolving_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicar revolvente"),
            "res_model": "l10n_pe.advance.revolving.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_view_generated_advances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Documentos generados"),
            "res_model": "l10n_pe.advance",
            "view_mode": "list,form",
            "domain": [("id", "in", self.advance_ids.ids)],
        }

    def action_view_compensated_revolvings(self):
        """Desde el asiento de compensacion: los REV usados."""
        self.ensure_one()
        revs = self.sudo().advance_application_ids.filtered(
            lambda a: a.application_type == "compensation"
        ).mapped("advance_id")
        return {
            "type": "ir.actions.act_window",
            "name": _("Revolventes"),
            "res_model": "l10n_pe.advance",
            "view_mode": "list,form",
            "domain": [("id", "in", revs.ids)],
        }

    def action_open_compensated_invoice(self):
        self.ensure_one()
        if not self.l10n_pe_compensated_invoice_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.l10n_pe_compensated_invoice_id.id,
            "view_mode": "form",
        }
