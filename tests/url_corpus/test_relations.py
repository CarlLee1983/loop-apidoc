from __future__ import annotations

from loop_apidoc.url_corpus import CorpusPage, UrlCorpus, find_related_pages


def test_find_related_pages_ranks_main_content_links_and_shared_entities():
    corpus = UrlCorpus(
        entry_url="https://docs.example.com/intro",
        pages=[
            CorpusPage(
                url="https://docs.example.com/action19",
                status="fetched",
                title="Cash transfer",
                body_file="body/action19.txt",
                internal_links=["https://docs.example.com/errors"],
                entities=["action:19", "error:9005"],
            ),
            CorpusPage(
                url="https://docs.example.com/errors",
                status="fetched",
                title="API errors",
                body_file="body/errors.txt",
                entities=["error:9005"],
            ),
            CorpusPage(
                url="https://docs.example.com/report",
                status="fetched",
                title="Reconciliation report",
                body_file="body/report.txt",
                internal_links=["https://docs.example.com/action19"],
            ),
            CorpusPage(
                url="https://docs.example.com/unrelated",
                status="fetched",
                title="Unrelated",
                body_file="body/unrelated.txt",
            ),
        ],
    )

    related = find_related_pages(corpus, "https://docs.example.com/action19")

    assert [candidate.url for candidate in related] == [
        "https://docs.example.com/errors",
        "https://docs.example.com/report",
    ]
    assert related[0].reasons == ["outbound_link", "shared_entity:error:9005"]
    assert related[1].reasons == ["inbound_link"]
    assert related[0].body_file == "body/errors.txt"


def test_find_related_pages_downweights_common_error_codes_and_prefers_the_same_branch():
    corpus = UrlCorpus(
        entry_url="https://docs.example.com/intro",
        pages=[
            CorpusPage(
                url="https://docs.example.com/transfer/action19", status="fetched",
                breadcrumb=["Transfer wallet", "Cash transfer"], entities=["error:9005"],
            ),
            CorpusPage(
                url="https://docs.example.com/z-transfer-errors", status="fetched",
                breadcrumb=["Transfer wallet", "Errors"], entities=["error:9005"],
            ),
            CorpusPage(
                url="https://docs.example.com/a-single-errors", status="fetched",
                breadcrumb=["Single wallet", "Errors"], entities=["error:9005"],
            ),
        ],
    )

    related = find_related_pages(corpus, "https://docs.example.com/transfer/action19")

    assert [candidate.url for candidate in related] == [
        "https://docs.example.com/z-transfer-errors",
        "https://docs.example.com/a-single-errors",
    ]
    assert related[0].reasons == ["same_branch", "shared_entity:error:9005"]
