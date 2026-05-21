import pytest
from datetime import datetime
from app import compute_proxima_entrevista, is_future_interview, ETAPA_ORDER, sort_key_latest_interview, format_proxima_fecha


class TestComputeProximaEntrevista:
    def test_no_interviews_returns_esperando(self):
        app = {'interviews': []}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'Esperando', 'next_fecha': '', 'next_hora': ''}

    def test_all_past_interviews_returns_esperando(self):
        app = {'interviews': [{'fecha_entrevista': '2026-05-01'}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'Esperando', 'next_fecha': '', 'next_hora': ''}

    def test_future_interview_returns_coordinada(self):
        app = {'interviews': [{'fecha_entrevista': '2026-07-01'}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'Coordinada', 'next_fecha': '2026-07-01', 'next_hora': ''}

    def test_today_counts_as_future(self):
        app = {'interviews': [{'fecha_entrevista': '2026-06-10'}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'Coordinada', 'next_fecha': '2026-06-10', 'next_hora': ''}

    def test_undated_interview_no_key_returns_a_coordinar(self):
        app = {'interviews': [{}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'A coordinar', 'next_fecha': '', 'next_hora': ''}

    def test_undated_interview_empty_string_returns_a_coordinar(self):
        app = {'interviews': [{'fecha_entrevista': ''}]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'A coordinar', 'next_fecha': '', 'next_hora': ''}

    def test_future_beats_undated(self):
        """If there is a future AND an undated interview, Coordinada wins."""
        app = {'interviews': [
            {'fecha_entrevista': '2026-07-01'},
            {'fecha_entrevista': ''},
        ]}
        assert compute_proxima_entrevista(app, datetime(2026, 6, 10, 12, 0)) == {'status': 'Coordinada', 'next_fecha': '2026-07-01', 'next_hora': ''}

    def test_today_with_past_hora_returns_esperando(self):
        """Interview today with hora already past (09:00 < noon) → Esperando."""
        app = {'interviews': [{'fecha_entrevista': '2026-06-10', 'hora_entrevista': '09:00'}]}
        now = datetime(2026, 6, 10, 12, 0)
        assert compute_proxima_entrevista(app, now) == {'status': 'Esperando', 'next_fecha': '', 'next_hora': ''}

    def test_today_with_future_hora_returns_coordinada(self):
        """Interview today with hora still upcoming (15:00 > noon) → Coordinada."""
        app = {'interviews': [{'fecha_entrevista': '2026-06-10', 'hora_entrevista': '15:00'}]}
        now = datetime(2026, 6, 10, 12, 0)
        assert compute_proxima_entrevista(app, now) == {'status': 'Coordinada', 'next_fecha': '2026-06-10', 'next_hora': '15:00'}

    def test_picks_earliest_future_interview(self):
        """When multiple future interviews exist, returns the earliest one."""
        app = {'interviews': [
            {'fecha_entrevista': '2026-08-01'},
            {'fecha_entrevista': '2026-07-01'},
        ]}
        now = datetime(2026, 6, 10, 12, 0)
        result = compute_proxima_entrevista(app, now)
        assert result['status'] == 'Coordinada'
        assert result['next_fecha'] == '2026-07-01'

    def test_picks_earliest_by_hora_when_same_date(self):
        """When two future interviews share the same date, picks the earlier hora."""
        app = {'interviews': [
            {'fecha_entrevista': '2026-07-01', 'hora_entrevista': '15:00'},
            {'fecha_entrevista': '2026-07-01', 'hora_entrevista': '09:00'},
        ]}
        now = datetime(2026, 6, 10, 12, 0)
        result = compute_proxima_entrevista(app, now)
        assert result['status'] == 'Coordinada'
        assert result['next_hora'] == '09:00'


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


class TestFormatProximaFecha:
    def test_date_only(self):
        # 2026-05-19 is a Tuesday (Martes)
        assert format_proxima_fecha('2026-05-19') == 'Martes 19/05/2026'

    def test_date_and_hora(self):
        assert format_proxima_fecha('2026-05-19', '14:30') == 'Martes 19/05/2026 14:30'

    def test_empty_fecha(self):
        assert format_proxima_fecha('') == ''

    def test_monday(self):
        # 2026-06-08 is a Monday (Lunes)
        assert format_proxima_fecha('2026-06-08') == 'Lunes 08/06/2026'

    def test_wednesday(self):
        # 2026-06-10 is a Wednesday (Miércoles)
        assert format_proxima_fecha('2026-06-10') == 'Miércoles 10/06/2026'

    def test_invalid_fecha_returns_as_is(self):
        assert format_proxima_fecha('not-a-date') == 'not-a-date'
