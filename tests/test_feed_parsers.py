"""Tests for the RSS and OAI-PMH feed parsers in ArxivClient."""

from datetime import datetime

import pytest

from arxiv_explorer.services.arxiv_client import ArxivClient

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:arxiv="http://arxiv.org/schemas/atom">
  <channel>
    <title>hep-ph, cs.AI updates on arXiv.org</title>
    <item>
      <title>Is Parity Violation a
Dynamical Effect?</title>
      <link>https://arxiv.org/abs/2606.02652</link>
      <description>arXiv:2606.02652v1 Announce Type: new
Abstract: As has been shown by multiple authors.  We reformulate.</description>
      <guid isPermaLink="false">oai:arXiv.org:2606.02652v1</guid>
      <category>hep-ph</category>
      <category>math-ph</category>
      <dc:creator>James H. Atwater, David Lambert, Yuri Rostovtsev</dc:creator>
      <arxiv:announce_type>new</arxiv:announce_type>
      <pubDate>Wed, 03 Jun 2026 00:00:00 -0400</pubDate>
    </item>
    <item>
      <title>A cross-listed paper</title>
      <link>https://arxiv.org/abs/2606.02700</link>
      <description>arXiv:2606.02700v1 Announce Type: cross
Abstract: Cross-list abstract.</description>
      <guid isPermaLink="false">oai:arXiv.org:2606.02700v1</guid>
      <category>cs.AI</category>
      <dc:creator>Jane Doe</dc:creator>
      <arxiv:announce_type>cross</arxiv:announce_type>
      <pubDate>Wed, 03 Jun 2026 00:00:00 -0400</pubDate>
    </item>
    <item>
      <title>A revised paper</title>
      <link>https://arxiv.org/abs/2601.00001</link>
      <description>arXiv:2601.00001v2 Announce Type: replace
Abstract: Old paper, new version.</description>
      <guid isPermaLink="false">oai:arXiv.org:2601.00001v2</guid>
      <category>hep-ph</category>
      <dc:creator>Old Author</dc:creator>
      <arxiv:announce_type>replace</arxiv:announce_type>
      <pubDate>Wed, 03 Jun 2026 00:00:00 -0400</pubDate>
    </item>
  </channel>
</rss>
"""

OAI_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <responseDate>2026-06-03T00:00:00Z</responseDate>
  <request verb="ListRecords" metadataPrefix="arXiv">https://oaipmh.arxiv.org/oai</request>
  <ListRecords>
    <record>
      <header>
        <identifier>oai:arXiv.org:2606.02652</identifier>
        <datestamp>2026-06-03</datestamp>
        <setSpec>physics:hep-ph</setSpec>
      </header>
      <metadata>
        <arXiv xmlns="http://arxiv.org/OAI/arXiv/">
          <id>2606.02652</id>
          <created>2026-06-03</created>
          <updated>2026-06-04</updated>
          <authors>
            <author><keyname>Atwater</keyname><forenames>James H.</forenames></author>
            <author><keyname>Lambert</keyname><forenames>David</forenames></author>
          </authors>
          <title>Is Parity Violation a
Dynamical Effect?</title>
          <categories>hep-ph math-ph</categories>
          <abstract>  As has been shown by multiple authors.
We reformulate the standard model.  </abstract>
        </arXiv>
      </metadata>
    </record>
    <record>
      <header status="deleted">
        <identifier>oai:arXiv.org:0000.00000</identifier>
        <datestamp>2026-06-03</datestamp>
      </header>
    </record>
    <resumptionToken cursor="0" completeListSize="100">TOKEN123</resumptionToken>
  </ListRecords>
</OAI-PMH>
"""


class TestParseRss:
    def test_keeps_only_new_and_cross(self):
        papers = ArxivClient()._parse_rss(RSS_SAMPLE)
        assert {p.arxiv_id for p in papers} == {"2606.02652v1", "2606.02700v1"}

    def test_fields_are_parsed(self):
        papers = ArxivClient()._parse_rss(RSS_SAMPLE)
        by_id = {p.arxiv_id: p for p in papers}
        p = by_id["2606.02652v1"]
        assert p.title == "Is Parity Violation a Dynamical Effect?"
        assert p.authors == ["James H. Atwater", "David Lambert", "Yuri Rostovtsev"]
        assert p.categories == ["hep-ph", "math-ph"]
        assert p.abstract.startswith("As has been shown")
        assert "Announce Type" not in p.abstract
        assert p.pdf_url == "https://arxiv.org/pdf/2606.02652v1"
        assert p.published == datetime(2026, 6, 3, 4, 0, 0)

    def test_empty_feed(self):
        assert ArxivClient()._parse_rss("<rss><channel></channel></rss>") == []


class TestParseOai:
    def test_skips_deleted_and_reads_token(self):
        papers, token = ArxivClient._parse_oai(OAI_SAMPLE)
        assert [p.arxiv_id for p in papers] == ["2606.02652"]
        assert token == "TOKEN123"

    def test_fields_are_parsed(self):
        papers, _ = ArxivClient._parse_oai(OAI_SAMPLE)
        p = papers[0]
        assert p.title == "Is Parity Violation a Dynamical Effect?"
        assert p.authors == ["James H. Atwater", "David Lambert"]
        assert p.categories == ["hep-ph", "math-ph"]
        assert p.abstract == "As has been shown by multiple authors. We reformulate the standard model."
        assert p.published == datetime(2026, 6, 3)
        assert p.updated == datetime(2026, 6, 4)
        assert p.pdf_url == "https://arxiv.org/pdf/2606.02652"

    def test_no_records_match_is_empty_not_error(self):
        xml = (
            '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
            '<error code="noRecordsMatch">no records</error></OAI-PMH>'
        )
        papers, token = ArxivClient._parse_oai(xml)
        assert papers == []
        assert token is None

    def test_other_error_raises(self):
        xml = (
            '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
            '<error code="badArgument">bad</error></OAI-PMH>'
        )
        with pytest.raises(RuntimeError):
            ArxivClient._parse_oai(xml)
