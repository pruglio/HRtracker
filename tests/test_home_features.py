import pytest
from datetime import datetime
from app import compute_proxima_entrevista, is_future_interview, ETAPA_ORDER, sort_key_latest_interview


class TestComputeProximaEntrevista:
    def test_no_interviews_returns_esperando(self):
        app = {'interviews': []}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'Esperando'

    def test_all_past_interviews_returns_esperando(self):
        app = {'interviews': [{'fecha_entrevista': '2026-05-01'}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'Esperando'

    def test_future_interview_returns_coordinada(self):
        app = {'interviews': [{'fecha_entrevista': '2026-07-01'}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'Coordinada'

    def test_today_counts_as_future(self):
        app = {'interviews': [{'fecha_entrevista': '2026-06-10'}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'Coordinada'

    def test_undated_interview_no_key_returns_a_coordinar(self):
        app = {'interviews': [{}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'A coordinar'

    def test_undated_interview_empty_string_returns_a_coordinar(self):
        app = {'interviews': [{'fecha_entrevista': ''}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'A coordinar'

    def test_future_beats_undated(self):
        """If there is a future AND an undated interview, Coordinada wins."""
        app = {'interviews': [
            {'fecha_entrevista': '2026-07-01'},
            {'fecha_entrevista': ''},
        ]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == 'Coordinada'

    def test_today_with_past_hora_returns_esperando(self):
        """Interview today with hora already past (09:00 < noon) → Esperando."""
        app = {'interviews': [{'fecha_entrevista': '2026-06-10', 'hora_entrevista': '09:00'}]}
        now = datetime(2026, 6, 10, 12, 0)
        assert compute_proxima_entrevista(app, now) == 'Esperando'

    def test_today_with_future_hora_returns_coordinada(self):
        """Interview today with hora still upcoming (15:00 > noon) → Coordinada."""
        app = {'interviews': [{'fecha_entrevista': '2026-06-10', 'hora_entrevista': '15:00'}]}
        now = datetime(2026, 6, 10, 12, 0)
        assert compute_proxima_entrevista(app, now) == 'Coordinada'


class TestIsFutureInterview:
    def test_no_fecha_returns_false(self):
        assert is_future_interview({}, datetime(2026, 6, 10, 12, 0)) is False

    def test_empty_fecha_returns_false(self):
        assert is_future_interview({'fecha_entrevista': ''}, datetime(2026, 6, 10, 12, 0)) is False

    def test_future_date_no_hora(self):
        iv = {'fecha_entrevista': '2026-07-01'}
        assert is_future_interview(iv, datetime(2026, 6, 10, 12, 0)) is True

    def test_past_date_no_hora(self):
        iv = {'fecha_entrevista': '2026-05-01'}
        assert is_future_interview(iv, datetime(2026, 6, 10, 12, 0)) is False

    def test_today_no_hora_counts_as_future(self):
        iv = {'fecha_entrevista': '2026-06-10'}
        assert is_future_interview(iv, datetime(2026, 6, 10, 12, 0)) is True

    def test_today_past_hora_returns_false(self):
        iv = {'fecha_entrevista': '2026-06-10', 'hora_entrevista': '09:00'}
        assert is_future_interview(iv, datetime(2026, 6, 10, 12, 0)) is False

    def test_today_future_hora_returns_true(self):
        iv = {'fecha_entrevista': '2026-06-10', 'hora_entrevista': '15:00'}
        assert is_future_interview(iv, datetime(2026, 6, 10, 12, 0)) is True

    def test_malformed_hora_falls_back_to_date_only(self):
        iv = {'fecha_entrevista': '2026-06-10', 'hora_entrevista': 'invalid'}
        assert is_future_interview(iv, datetime(2026, 6, 10, 12, 0)) is True


class TestEtapaOrder:
    def test_oferta_beats_aplicado(self):
        assert ETAPA_ORDER['Oferta'] < ETAPA_ORDER['Aplicado']

    def test_rechazado_after_aplicado(self):
        assert ETAPA_ORDER['Rechazado'] > ETAPA_ORDER['Aplicado']

    def test_descartado_is_last(self):
        assert ETAPA_ORDER['Descartado'] == max(ETAPA_ORDER.values())

    def test_oferta_is_first(self):
        assert ETAPA_ORDER['Oferta'] == min(ETAPA_ORDER.values())

    def test_stage_sort_order(self):
        """Two-pass stable sort puts advanced stages first."""
        apps = [
            {'etapa': 'Aplicado', 'interviews': []},
            {'etapa': 'Oferta', 'interviews': []},
            {'etapa': 'Final', 'interviews': []},
            {'etapa': 'Rechazado', 'interviews': []},
        ]
        apps.sort(key=sort_key_latest_interview, reverse=True)
        apps.sort(key=lambda a: ETAPA_ORDER.get(a.get('etapa', ''), 99))
        assert [a['etapa'] for a in apps] == ['Oferta', 'Final', 'Aplicado', 'Rechazado']
