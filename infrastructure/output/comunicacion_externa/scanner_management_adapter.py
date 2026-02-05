import requests
import logging

class ScannerManagementAdapter:
    def __init__(self, base_url="http://localhost:8080/api/escaner"):
        self.base_url = base_url
        self.logger = logging.getLogger(__name__)

    def obtener_escaneres_activos(self):
        """
        Consulta el endpoint /iniciados del servicio de gestion de escaneres.
        Retorna una lista de diccionarios (escaneres).
        """
        try:
            url = f"{self.base_url}/iniciados"
            self.logger.info(f"Consultando escaneres activos en: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            escaneres = response.json()
            self.logger.info(f"Se obtuvieron {len(escaneres)} escaneres activos.")
            return escaneres
        except Exception as e:
            self.logger.error(f"Error obteniendo escaneres activos: {e}")
            return []
