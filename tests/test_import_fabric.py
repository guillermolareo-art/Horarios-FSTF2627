"""
Tests de la seudonimizacion de import_fabric.py.

Lo que se protege aqui no es una preferencia de formato: es que un nombre
propio de cadete no llegue nunca al JSON publicado. El job de GitHub Actions
publica sin revision humana, asi que esta es la unica barrera que hay.

Los nombres de este archivo son inventados a proposito. No se usan los de
ninguna sabana real: un test tambien es codigo publicado.
"""
from scripts.import_fabric import (
    ClaseFabric,
    agrupar,
    construir_seudonimos,
    es_grupo_colectivo,
)


def clase(dia="Lunes", inicio="08:15", fin="09:05", tipo="TEORIA", aula=40,
          grupos=(), columna=1, anotacion=None):
    return ClaseFabric(dia=dia, inicio=inicio, fin=fin, tipo=tipo, aula=aula,
                       grupos=tuple(grupos), fila_origen=10, columna_origen=columna,
                       anotacion_fila1=anotacion)


class TestFormaDeLaEtiqueta:
    def test_grupos_colectivos_se_reconocen(self):
        for etiqueta in ("G1", "G6", "G1A", "G3B", "IM1", "IM2",
                         "G1 (4 CGA-ST)", "IM2 (4 CIM-ST)", "g4"):
            assert es_grupo_colectivo(etiqueta), etiqueta

    def test_un_nombre_propio_no_es_un_grupo(self):
        for etiqueta in ("ZORRILLA_DEL_VALLE", "MARLOWE", "Chen", "GM2o"):
            assert not es_grupo_colectivo(etiqueta), etiqueta

    def test_ante_la_duda_se_seudonimiza(self):
        # Una etiqueta que no encaja en la forma conocida se trata como
        # persona aunque pudiera ser un grupo nuevo: el coste de equivocarse
        # en un sentido es un "Cadete 1" de mas; en el otro, publicar un nombre.
        assert not es_grupo_colectivo("GRUPO NUEVO 2028")


class TestSeudonimos:
    def test_solo_las_personas_reciben_seudonimo(self):
        m = construir_seudonimos(["G1 (4 CGA-ST)", "MARLOWE", "IM1 (4 CIM-ST)"])
        assert m == {"MARLOWE": "Cadete 1"}

    def test_cada_persona_recibe_uno_distinto(self):
        m = construir_seudonimos(["MARLOWE", "Chen", "ZORRILLA_DEL_VALLE"])
        assert len(set(m.values())) == 3

    def test_es_estable_entre_ejecuciones(self):
        etiquetas = ["Chen", "G2 (4 CGA-ST)", "MARLOWE"]
        assert construir_seudonimos(etiquetas) == construir_seudonimos(reversed(etiquetas))


class TestSalidaPublicada:
    def test_ningun_nombre_llega_al_json(self):
        clases = [
            clase(grupos=["G5 (4 CGA-ST)", "MARLOWE", "Chen"]),
            clase(inicio="10:20", fin="11:10", grupos=["Chen"]),
        ]
        salida, _ = agrupar(clases)
        texto = repr(salida)
        for nombre in ("MARLOWE", "Chen"):
            assert nombre not in texto
        assert "G5 (4 CGA-ST)" in texto

    def test_la_misma_persona_mantiene_su_seudonimo_en_todas_sus_franjas(self):
        clases = [
            clase(grupos=["MARLOWE", "Chen"]),
            clase(inicio="10:20", fin="11:10", grupos=["Chen"]),
        ]
        salida, _ = agrupar(clases)
        primera = {g.strip() for g in salida[0]["grupos"].split(",")}
        segunda = {g.strip() for g in salida[1]["grupos"].split(",")}
        assert segunda <= primera
        assert len(segunda) == 1

    def test_dos_personas_distintas_no_se_funden(self):
        # Si colapsaran en una sola etiqueta, merge_schedule las veria como un
        # grupo compartido y denunciaria un solapamiento que no existe.
        clases = [
            clase(grupos=["MARLOWE"], aula=40),
            clase(grupos=["Chen"], aula=45, columna=2),
        ]
        salida, _ = agrupar(clases)
        assert salida[0]["grupos"] != salida[1]["grupos"]

    def test_los_avisos_tampoco_reproducen_nombres(self):
        clases = [
            clase(grupos=["MARLOWE"], anotacion="PORTUGUESES"),
            clase(grupos=["G1 (4 CGA-ST)", "G1 (4 CGA-ST)"]),
        ]
        _, avisos = agrupar(clases)
        assert avisos
        texto = " ".join(avisos)
        assert "MARLOWE" not in texto
        assert "PORTUGUESES" not in texto

    def test_un_aviso_de_anotacion_dice_en_que_columna_mirar(self):
        clases = [clase(grupos=["G4 (4 CGA-ST)"], columna=31, anotacion="BREST")]
        _, avisos = agrupar(clases)
        assert any("columna 31" in a for a in avisos)
