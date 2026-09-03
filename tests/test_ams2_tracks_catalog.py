from circuit_stackers.ams2_tracks_catalog import match_tracks, parse_wiki_tracks


def test_parse_wiki_tracks() -> None:
    html = """
    <table><tr><th>Country</th><th>Track</th><th>Layout</th><th>Year</th></tr>
    <tr><td>USA</td><td>Daytona</td><td>Daytona Road Course</td><td>2020</td></tr></table>
    """

    assert parse_wiki_tracks(html) == [{"track": "Daytona", "layout": "Daytona Road Course"}]


def test_match_tracks() -> None:
    matches = match_tracks(
        [{"track": "Daytona", "layout": "Daytona Road Course"}],
        [{"Track": "Daytona", "Layout": "Daytona Road Course", "Game": "AMS2"}],
    )

    assert matches[0].local_track == "Daytona"
