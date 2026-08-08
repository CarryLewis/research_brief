from .email_imap import EmailConnector
from .manual import ManualConnector
from .pubmed import PubMedConnector
from .rss import RssConnector
from .web import WebConnector
from .wechat import WeChatConnector

CONNECTORS = {
    "manual": ManualConnector(),
    "pubmed": PubMedConnector(),
    "rss": RssConnector(),
    "email": EmailConnector(),
    "web": WebConnector(),
    "wechat": WeChatConnector(),
}

__all__ = [
    "CONNECTORS",
    "ManualConnector",
    "PubMedConnector",
    "RssConnector",
    "EmailConnector",
    "WebConnector",
    "WeChatConnector",
]
