import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timezone

from app.config import settings
from app.core.fundamentals_cache import FundamentalsCache
from app.core.gestor_barras import GestorBarras
from app.core.gestor_tiempo import GestorTiempo
from app.core.worker_filtros import evaluar_simbolos
from app.domain.enums import (
    SCANNER_TF_A_MARKETDATA,
    TIMEFRAME_INTERVALO_SEG,
    EnumTimeframe,
)
from app.domain.models.contexto_simbolo import ContextoSimbolo
from app.domain.models.escaner import Escaner
from app.domain.models.vela import Vela
from app.infrastructure.output.kafka_producer_adapter import KafkaProducerAdapter
from app.infrastructure.output.marketdata_rest_adapter import MarketdataRestAdapter

logger = logging.getLogger(__name__)


class EjecutorEscaner:
    """Ejecuta un escáner individual en un loop async."""

    def __init__(
        self,
        escaner: Escaner,
        kafka_producer: KafkaProducerAdapter,
        marketdata_rest: MarketdataRestAdapter,
        process_pool: ProcessPoolExecutor,
        gestor_tiempo: GestorTiempo,
        fundamentals_cache: FundamentalsCache | None = None,
        halt_monitor=None,
    ):
        self._escaner = escaner
        self._kafka = kafka_producer
        self._marketdata = marketdata_rest
        self._pool = process_pool
        self._gestor_tiempo = gestor_tiempo
        self._fundamentals_cache = fundamentals_cache
        self._halt_monitor = halt_monitor
        self._contextos: dict[str, ContextoSimbolo] = {}
        self._activo = True
        self._ultima_fecha_fundamentales: date | None = None
        self._ultimo_conteo_filtrado: int | None = None
        self._ultimos_logs: dict[str, str] = {}
        self._ultimos_simbolos_filtrados: frozenset | None = None
        # Timeframes determinados en ejecutar() y reutilizados en toda la sesión
        self._timeframes: list[EnumTimeframe] = []
        self._tf_min: EnumTimeframe = EnumTimeframe.M5

    async def ejecutar(self):
        """Método principal ejecutado como asyncio.Task."""
        escaner = self._escaner
        gt = self._gestor_tiempo

        # 1. Determinar todos los timeframes únicos de los filtros
        self._timeframes, self._tf_min = self._determinar_timeframes()
        intervalo_seg = TIMEFRAME_INTERVALO_SEG[self._tf_min]
        tf_nombres = [tf.value for tf in self._timeframes]

        logger.info(
            "Escaner %d '%s': timeframes=%s (min=%s), mercados=%s",
            escaner.id_escaner, escaner.nombre, tf_nombres, self._tf_min.value, escaner.mercados,
        )

        # 2. Esperar primera ventana de trading antes de tocar marketdata
        if not await self._esperar_ventana_trading():
            return

        # 3. Cargar datos para la sesión actual
        if not await self._iniciar_sesion():
            return

        # 4. Loop principal
        while self._activo:
            ahora = gt.ahora_utc()
            fecha_hoy = ahora.date()
            hora_actual = ahora.time()

            # 4a. Verificar hora_fin
            if hora_actual >= escaner.hora_fin:
                logger.info(
                    "Escaner %d: hora_fin alcanzada (%s)",
                    escaner.id_escaner, escaner.hora_fin,
                )
                if escaner.tipo_ejecucion == "UNA_VEZ":
                    await self._kafka.publicar_cambio_estado(
                        escaner.id_escaner, escaner.nombre,
                        "INICIADO", "DETENIDO",
                        "ESCANER_UNA_VEZ completado",
                    )
                    break

                # DIARIA: dormir hasta hora_inicio del siguiente día hábil
                siguiente = gt.siguiente_dia_habil(escaner.mercados, fecha_hoy)
                objetivo = gt.construir_datetime_utc(escaner.hora_inicio, siguiente)
                logger.info(
                    "Escaner %d: DIARIA, durmiendo hasta %s",
                    escaner.id_escaner, objetivo.isoformat(),
                )
                await self._kafka.publicar_log(
                    escaner.id_escaner, "INFO",
                    f"Escáner {escaner.nombre}: sesión finalizada. Próximo inicio programado para el {siguiente} a las {escaner.hora_inicio} UTC",
                    categoria="LIFECYCLE"
                )
                await gt.dormir_hasta(objetivo)

                # Nueva sesión: recargar símbolos y barras frescas
                if self._activo:
                    if not await self._iniciar_sesion():
                        break
                continue

            # 4b. Esperar próximo cierre de vela del TF mínimo
            espera = gt.calcular_espera_vela(intervalo_seg, settings.margen_cierre_vela_seg)
            logger.debug(
                "Escaner %d: esperando %.1fs para próxima vela (%s)",
                escaner.id_escaner, espera, self._tf_min.value,
            )
            await asyncio.sleep(espera)

            if not self._activo:
                break

            # 4c. Obtener la última vela para TODOS los timeframes en paralelo
            simbolos_activos = list(self._contextos.keys())
            resultados = await asyncio.gather(*[
                self._marketdata.obtener_ultima_vela_batch(simbolos_activos, tf.value)
                for tf in self._timeframes
            ])

            # Actualizar barras por TF
            for tf, nuevas_velas in zip(self._timeframes, resultados):
                tf_str = tf.value
                for symbol, vela_data in nuevas_velas.items():
                    if symbol not in self._contextos:
                        continue
                    ctx = self._contextos[symbol]
                    nuevo_ts = vela_data.get("timestamp", "")
                    if nuevo_ts and nuevo_ts != ctx.ultima_vela_por_tf.get(tf_str):
                        vela = Vela.desde_dict(vela_data, symbol)
                        df_actual = ctx.barras_por_tf.get(
                            tf_str, GestorBarras.crear_dataframe_desde_velas([])
                        )
                        ctx.barras_por_tf[tf_str] = GestorBarras.agregar_vela(df_actual, vela)
                        ctx.ultima_vela_por_tf[tf_str] = nuevo_ts

            # 4d. Evaluar filtros y publicar señales
            await self._evaluar_y_publicar()

        logger.info("Escaner %d: loop finalizado", escaner.id_escaner)

    async def _esperar_ventana_trading(self) -> bool:
        """Espera hasta que sea el momento correcto para operar."""
        escaner = self._escaner
        gt = self._gestor_tiempo

        while self._activo:
            ahora = gt.ahora_utc()
            fecha_hoy = ahora.date()

            if not all(gt.es_dia_habil(m, fecha_hoy) for m in escaner.mercados):
                siguiente = gt.siguiente_dia_habil(escaner.mercados, fecha_hoy)
                objetivo = gt.construir_datetime_utc(escaner.hora_inicio, siguiente)
                logger.info(
                    "Escaner %d: mercado cerrado hoy (%s), esperando hasta %s",
                    escaner.id_escaner, fecha_hoy, objetivo.isoformat(),
                )
                await self._kafka.publicar_log(
                    escaner.id_escaner, "INFO",
                    f"Escáner {escaner.nombre}: mercado cerrado ({fecha_hoy}), inicia el {siguiente}",
                )
                await gt.dormir_hasta(objetivo)
                continue

            hora_actual = ahora.time()

            if hora_actual >= escaner.hora_fin:
                if escaner.tipo_ejecucion == "UNA_VEZ":
                    logger.warning(
                        "Escaner %d: hora_fin ya pasó hoy, UNA_VEZ no se ejecutará",
                        escaner.id_escaner,
                    )
                    await self._kafka.publicar_cambio_estado(
                        escaner.id_escaner, escaner.nombre,
                        "INICIADO", "DETENIDO",
                        "ESCANER_UNA_VEZ completado",
                    )
                    return False
                siguiente = gt.siguiente_dia_habil(escaner.mercados, fecha_hoy)
                objetivo = gt.construir_datetime_utc(escaner.hora_inicio, siguiente)
                logger.info(
                    "Escaner %d: ventana de hoy ya cerró, esperando hasta %s",
                    escaner.id_escaner, objetivo.isoformat(),
                )
                await gt.dormir_hasta(objetivo)
                continue

            if hora_actual < escaner.hora_inicio:
                objetivo = gt.construir_datetime_utc(escaner.hora_inicio, fecha_hoy)
                logger.info(
                    "Escaner %d: esperando hora_inicio %s (UTC)",
                    escaner.id_escaner, escaner.hora_inicio,
                )
                await self._kafka.publicar_log(
                    escaner.id_escaner, "INFO",
                    f"Escáner {escaner.nombre}: inicia a las {escaner.hora_inicio} UTC",
                )
                await gt.dormir_hasta(objetivo)
                continue

            return True

        return False

    async def _iniciar_sesion(self) -> bool:
        """Carga símbolos, fundamentales y barras históricas para todos los TFs.

        Retorna False si no se encontraron símbolos.
        """
        escaner = self._escaner

        simbolos = await self._marketdata.obtener_simbolos_por_mercados(escaner.mercados)
        if not simbolos:
            await self._kafka.publicar_log(
                escaner.id_escaner, "WARN",
                f"Escáner {escaner.nombre}: no se encontraron símbolos para {escaner.mercados}",
            )
            return False

        logger.info("Escaner %d: %d símbolos cargados para la sesión", escaner.id_escaner, len(simbolos))
        tf_nombres = [tf.value for tf in self._timeframes]
        await self._kafka.publicar_log(
            escaner.id_escaner, "INFO",
            f"Fase 1: Lista de símbolos obtenida ({len(simbolos)} activos). "
            f"Iniciando carga de barras para timeframes {tf_nombres}...",
            categoria="INITIALIZATION"
        )

        # Inicializar contextos vacíos
        self._contextos = {
            symbol: ContextoSimbolo(symbol=symbol)
            for symbol in simbolos
        }

        # Cargar barras históricas para TODOS los timeframes en paralelo
        resultados = await asyncio.gather(*[
            self._marketdata.obtener_barras_batch(simbolos, tf.value, bars=200)
            for tf in self._timeframes
        ])

        # Poblar barras_por_tf en orden ascendente de intervalo (primer key = TF mínimo)
        for tf, barras_por_simbolo in zip(self._timeframes, resultados):
            tf_str = tf.value
            for symbol in simbolos:
                velas_raw = barras_por_simbolo.get(symbol, [])
                df = GestorBarras.crear_dataframe_desde_velas(velas_raw)
                self._contextos[symbol].barras_por_tf[tf_str] = df
                self._contextos[symbol].ultima_vela_por_tf[tf_str] = (
                    velas_raw[-1].get("timestamp") if velas_raw else None
                )

        simbolos_con_datos = sum(
            1 for ctx in self._contextos.values() if ctx.tiene_barras()
        )
        await self._kafka.publicar_log(
            escaner.id_escaner, "INFO",
            f"Fase 1 completada: barras cargadas para {simbolos_con_datos}/{len(simbolos)} símbolos "
            f"en {len(self._timeframes)} timeframe(s). Cargando fundamentales...",
            categoria="INITIALIZATION",
        )

        await self._refrescar_fundamentales(simbolos)

        await self._kafka.publicar_log(
            escaner.id_escaner, "INFO",
            f"Escáner {escaner.nombre}: sesión iniciada con {len(simbolos)} símbolos, "
            f"timeframes {tf_nombres}",
        )
        return True

    async def _refrescar_fundamentales(self, simbolos: list[str]) -> None:
        """Refresca el caché de fundamentales y actualiza los contextos."""
        if not self._fundamentals_cache or not simbolos:
            return
        mercado = self._escaner.mercados[0] if self._escaner.mercados else "NYSE"

        await self._fundamentals_cache.refrescar(simbolos, mercado)

        con_datos = 0
        for sym in simbolos:
            if sym in self._contextos:
                fund = self._fundamentals_cache.obtener(sym)
                self._contextos[sym].fundamentales = fund
                if fund:
                    con_datos += 1

        self._ultima_fecha_fundamentales = datetime.now(timezone.utc).date()
        logger.debug(
            "Escaner %d: fundamentales actualizados para %d símbolos",
            self._escaner.id_escaner, len(simbolos),
        )
        await self._kafka.publicar_log(
            self._escaner.id_escaner, "INFO",
            f"Fase 2: Fundamentales cargados. {con_datos} símbolos con información, "
            f"{len(simbolos) - con_datos} ignorados por falta de datos.",
            categoria="INITIALIZATION"
        )

    async def _evaluar_y_publicar(self):
        """Evalúa filtros en el pool de procesos y publica señales."""
        escaner = self._escaner

        # Inyectar estado de halt en los contextos antes de serializar
        if self._halt_monitor:
            for sym, ctx in self._contextos.items():
                ctx.halteado = self._halt_monitor.esta_halteado(sym)

        contextos_ser = {
            symbol: ctx.a_dict_serializable()
            for symbol, ctx in self._contextos.items()
            if ctx.tiene_barras()
        }

        filtros_ser = []
        for f in escaner.filtros:
            parametros_ser = []
            for p in f.parametros:
                parametros_ser.append({
                    "enum_parametro": p.enum_parametro,
                    "obj_valor_seleccionado": p.obj_valor_seleccionado,
                })
            filtros_ser.append({
                "enum_filtro": f.enum_filtro,
                "parametros": parametros_ser,
            })

        if not contextos_ser or not filtros_ser:
            return

        loop = asyncio.get_event_loop()
        try:
            senales = await loop.run_in_executor(
                self._pool,
                evaluar_simbolos,
                contextos_ser,
                filtros_ser,
                escaner.id_escaner,
                escaner.nombre,
            )
        except Exception as e:
            logger.error("Error evaluando filtros para escaner %d: %s", escaner.id_escaner, e)
            await self._kafka.publicar_log(
                escaner.id_escaner, "ERROR",
                f"Error evaluando filtros: {str(e)[:200]}",
                categoria="EVALUATION",
            )
            return

        simbolos_que_pasaron = [s["symbol"] for s in senales if s.get("tipoSenal") == "ALERTA_FILTROS"]
        conteo_actual = len(simbolos_que_pasaron)

        simbolos_set = frozenset(simbolos_que_pasaron)
        if simbolos_set != self._ultimos_simbolos_filtrados:
            self._ultimos_simbolos_filtrados = simbolos_set
            await self._kafka.publicar_simbolos_filtrados(escaner.id_escaner, simbolos_que_pasaron)

        if conteo_actual != self._ultimo_conteo_filtrado:
            await self._publicar_log_dedup(
                "INFO",
                f"Fase de Evaluación: {conteo_actual} símbolos cumplen con las estrategias actualmente.",
                categoria="EVALUATION",
            )
            self._ultimo_conteo_filtrado = conteo_actual

        for senal in senales:
            senal["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            await self._kafka.publicar_senal(senal)

        if senales:
            await self._publicar_log_dedup(
                "INFO",
                f"Escáner {escaner.nombre}: {len(senales)} señales generadas",
                categoria="SCANNER",
            )

    def _determinar_timeframes(self) -> tuple[list[EnumTimeframe], EnumTimeframe]:
        """Determina todos los timeframes únicos de los filtros, ordenados ascendente.

        Returns:
            (lista ordenada por intervalo ascendente, timeframe mínimo)
        """
        encontrados: set[EnumTimeframe] = set()

        for filtro in self._escaner.filtros:
            tf_str = filtro.obtener_timeframe()
            if tf_str and tf_str in SCANNER_TF_A_MARKETDATA:
                encontrados.add(SCANNER_TF_A_MARKETDATA[tf_str])
            elif tf_str:
                logger.warning(
                    "Escaner %d '%s': filtro '%s' tiene timeframe '%s' no soportado. Ignorado.",
                    self._escaner.id_escaner, self._escaner.nombre,
                    filtro.enum_filtro, tf_str,
                )

        if not encontrados:
            logger.warning(
                "Escaner %d '%s': ningún filtro tiene timeframe — usando M5 por defecto.",
                self._escaner.id_escaner, self._escaner.nombre,
            )
            tf_default = EnumTimeframe.M5
            return [tf_default], tf_default

        tf_lista = sorted(encontrados, key=lambda tf: TIMEFRAME_INTERVALO_SEG[tf])
        return tf_lista, tf_lista[0]

    async def _publicar_log_dedup(
        self,
        nivel: str,
        mensaje: str,
        categoria: str = "SCANNER",
        tipo: str = "SCANNER_STATE",
    ) -> None:
        """Publica el log solo si el mensaje cambió respecto al último envío en esa categoría."""
        if self._ultimos_logs.get(categoria) == mensaje:
            return
        self._ultimos_logs[categoria] = mensaje
        await self._kafka.publicar_log(self._escaner.id_escaner, nivel, mensaje, categoria, tipo)

    def detener(self):
        self._activo = False
