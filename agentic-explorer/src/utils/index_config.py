"""
Centrale configuratie voor Elasticsearch indexnamen.
Alle agents kunnen deze configuratie gebruiken om de juiste indexnamen te verkrijgen.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class IndexConfig:
    """Configuratie voor een Elasticsearch index."""

    name: str
    chunks_name: Optional[str] = None
    embedding_field: str = "embedding_summary"
    chunks_embedding_field: str = "embedding"
    description: str = ""


class ElasticsearchIndices:
    """Centrale configuratie voor alle Elasticsearch indexnamen."""

    # CVDR - Centrale Voorziening Decentrale Regelgeving
    CVDR = IndexConfig(
        name="cvdr_document_v1_27300",
        chunks_name="cvdr_document_chunks_v1_27300",
        embedding_field="embedding_summary",
        chunks_embedding_field="embedding",
        description="Lokale wetgeving, APV, verordeningen, leges",
    )

    # Web - Website content
    WEB = IndexConfig(
        name="web_document_v1_27300",
        chunks_name="web_document_chunks_v1_27300",
        embedding_field="embedding_summary",
        chunks_embedding_field="embedding",
        description="Website content, procedures, formulieren, nieuws",
    )

    # OEP - Officiële Publicaties
    OEP = IndexConfig(
        name="oep_document_v1_27300",
        chunks_name="oep_document_chunks_v1_27300",
        embedding_field="embedding_summary",
        chunks_embedding_field="embedding",
        description="Officiële publicaties, vergunningen, besluiten",
    )

    # ROO - Register van Overheidsorganisaties
    ROO = IndexConfig(
        name="roo_document_v1",
        chunks_name=None,  # ROO heeft geen chunks
        embedding_field="embedding_summary",
        chunks_embedding_field="embedding",
        description="Overheidsorganisaties, contactgegevens, structuur",
    )

    @classmethod
    def get_all_indices(cls) -> dict[str, IndexConfig]:
        """Verkrijg alle beschikbare indices."""
        return {
            "CVDR": cls.CVDR,
            "WEB": cls.WEB,
            "OEP": cls.OEP,
            "ROO": cls.ROO,
        }

    @classmethod
    def get_cross_index_config(cls, primary: str = "CVDR") -> dict[str, IndexConfig]:
        """
        Verkrijg configuratie voor cross-index zoeken.

        Args:
            primary: De primaire index om mee te beginnen

        Returns:
            Dictionary met alle indices, primaire index eerst
        """
        all_indices = cls.get_all_indices()

        if primary not in all_indices:
            raise ValueError(
                f"Onbekende primaire index: {primary}. Beschikbaar: {list(all_indices.keys())}"
            )

        # Zet primaire index eerst
        result = {primary: all_indices[primary]}

        # Voeg andere indices toe
        for name, config in all_indices.items():
            if name != primary:
                result[name] = config

        return result


# Convenience functies voor backward compatibility
def get_cvdr_index() -> IndexConfig:
    """Verkrijg CVDR index configuratie."""
    return ElasticsearchIndices.CVDR


def get_web_index() -> IndexConfig:
    """Verkrijg Web index configuratie."""
    return ElasticsearchIndices.WEB


def get_oep_index() -> IndexConfig:
    """Verkrijg OEP index configuratie."""
    return ElasticsearchIndices.OEP


def get_roo_index() -> IndexConfig:
    """Verkrijg ROO index configuratie."""
    return ElasticsearchIndices.ROO
