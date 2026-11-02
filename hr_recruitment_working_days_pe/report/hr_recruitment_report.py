# -*- coding: utf-8 -*-
from odoo import fields, models


# SQL: calcula el domingo de Pascua (algoritmo de Butcher/Gregoriano)
_EASTER_FUNC = """
CREATE OR REPLACE FUNCTION easter_date_pe(p_year INT) RETURNS DATE AS $$
DECLARE
    a INT := p_year % 19;
    b INT := p_year / 100;
    c INT := p_year % 100;
    d INT := b / 4;
    e INT := b % 4;
    f INT := (b + 8) / 25;
    g INT := (b - f + 1) / 3;
    h INT := (19*a + b - d - g + 15) % 30;
    i INT := c / 4;
    k INT := c % 4;
    l INT := (32 + 2*e + 2*i - h - k) % 7;
    m INT := (a + 11*h + 22*l) / 451;
    v_month INT := (h + l - 7*m + 114) / 31;
    v_day   INT := ((h + l - 7*m + 114) % 31) + 1;
BEGIN
    RETURN make_date(p_year, v_month, v_day);
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
"""

# SQL: cuenta días hábiles entre dos fechas según el calendario de Perú.
# Excluye: sábados, domingos, 11 feriados fijos y Jueves/Viernes Santo.
_BUSINESS_DAYS_FUNC = """
CREATE OR REPLACE FUNCTION business_days_pe(start_d DATE, end_d DATE) RETURNS INT AS $$
DECLARE
    result INT;
    p_year INT;
BEGIN
    IF start_d IS NULL OR end_d IS NULL OR end_d < start_d THEN
        RETURN NULL;
    END IF;
    IF end_d = start_d THEN
        RETURN 0;
    END IF;

    SELECT COUNT(*)::INT INTO result
    FROM generate_series(start_d, end_d - 1, '1 day'::interval) AS d(day)
    WHERE
        -- Excluir domingo (0) y sábado (6)
        EXTRACT(DOW FROM d.day) NOT IN (0, 6)
        -- Excluir feriados oficiales del Perú
        AND d.day::date NOT IN (
            -- Feriados FIJOS
            make_date(EXTRACT(YEAR FROM d.day)::INT,  1,  1),  -- Año Nuevo
            make_date(EXTRACT(YEAR FROM d.day)::INT,  5,  1),  -- Día del Trabajo
            make_date(EXTRACT(YEAR FROM d.day)::INT,  6, 29),  -- San Pedro y San Pablo
            make_date(EXTRACT(YEAR FROM d.day)::INT,  7, 28),  -- Independencia del Perú
            make_date(EXTRACT(YEAR FROM d.day)::INT,  7, 29),  -- Gran Parada Militar
            make_date(EXTRACT(YEAR FROM d.day)::INT,  8, 30),  -- Santa Rosa de Lima
            make_date(EXTRACT(YEAR FROM d.day)::INT, 10,  8),  -- Combate de Angamos
            make_date(EXTRACT(YEAR FROM d.day)::INT, 11,  1),  -- Todos los Santos
            make_date(EXTRACT(YEAR FROM d.day)::INT, 12,  8),  -- Inmaculada Concepción
            make_date(EXTRACT(YEAR FROM d.day)::INT, 12,  9),  -- Batalla de Ayacucho
            make_date(EXTRACT(YEAR FROM d.day)::INT, 12, 25),  -- Navidad
            -- Semana Santa (variable): Jueves Santo y Viernes Santo
            easter_date_pe(EXTRACT(YEAR FROM d.day)::INT) - 3,  -- Jueves Santo
            easter_date_pe(EXTRACT(YEAR FROM d.day)::INT) - 2   -- Viernes Santo
        );

    RETURN result;
END;
$$ LANGUAGE plpgsql IMMUTABLE STRICT;
"""


class HrRecruitmentReport(models.Model):
    _inherit = 'hr.recruitment.report'

    working_days_duration = fields.Integer(
        string='Duración (días hábiles PE)',
        aggregator='avg',
        readonly=True,
    )

    def _query(self, fields='', from_clause=''):
        fields += """
            , CASE
                WHEN a.date_closed IS NOT NULL
                THEN business_days_pe(
                    a.create_date::date,
                    (a.create_date::date
                        + date_part('day', a.date_closed - a.create_date)::int
                    )::date
                )
                ELSE NULL
              END AS working_days_duration
        """
        return super()._query(fields, from_clause)

    def init(self):
        # Instalar las funciones PostgreSQL antes de recrear la vista
        self.env.cr.execute(_EASTER_FUNC)
        self.env.cr.execute(_BUSINESS_DAYS_FUNC)
        super().init()
