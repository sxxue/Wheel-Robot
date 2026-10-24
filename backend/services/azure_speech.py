import logging
from backend.config import settings

logger = logging.getLogger(__name__)

class AzureSpeechService:
    def __init__(self):
        self.use_mock = settings.USE_MOCK_AZURE or not bool(settings.AZURE_SPEECH_KEY)
        self.speech_key = settings.AZURE_SPEECH_KEY
        self.speech_region = settings.AZURE_SPEECH_REGION

    def get_speech_config(self):
        """Returns client configuration or token status for web client"""
        if self.use_mock:
            return {
                "is_mock": True,
                "region": self.speech_region,
                "status": "Mock Mode (Uses browser Web Speech API or manual text)"
            }
        return {
            "is_mock": False,
            "region": self.speech_region,
            "status": "Azure Speech Services Ready"
        }

azure_speech_service = AzureSpeechService()
