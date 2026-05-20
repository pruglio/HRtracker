import pytest
from app import compute_proxima_entrevista, ETAPA_ORDER, sort_key_latest_interview


class TestComputeProximaEntrevista:
    def test_no_interviews_returns_esperando(self):
        app = {'interviews': []}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Esperando'

    def test_all_past_interviews_returns_esperando(self):
        app = {'interviews': [{'fecha_entrevista': '2026-05-01'}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Esperando'

    def test_future_interview_returns_coordinada(self):
        app = {'interviews': [{'fecha_entrevista': '2026-07-01'}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Coordinada'

    def test_today_counts_as_future(self):
        app = {'interviews': [{'fecha_entrevista': '2026-06-01'}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Coordinada'

    def test_undated_interview_no_key_returns_a_coordinar(self):
        app = {'interviews': [{}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'A coordinar'

    def test_undated_interview_empty_string_returns_a_coordinar(self):
        app = {'interviews': [{'fecha_entrevista': ''}]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'A coordinar'

    def test_future_beats_undated(self):
        """If there is a future AND an undated interview, Coordinada wins."""
        app = {'interviews': [
            {'fecha_entrevista': '2026-07-01'},
            {'fecha_entrevista': ''},
        ]}
        assert compute_proxima_entrevista(app, '2026-06-01') == 'Coordinada'


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
