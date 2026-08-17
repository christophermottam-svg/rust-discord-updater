from src.scraper import ArticleImage, PatchSection, extract_latest_patch, match_section_images


HTML = """
<html><body>
<div>Patch Name</div><div>February Update</div>
<div>Changelist Title</div><div>February 2026</div>
<div>date_range</div><div>2026-02-05</div>
<h2>Features</h2>
<div>New fishing boat storage</div>
<div>Improved fishing UI</div>
<h2>Fixed</h2>
<div>Fixed a crash when entering a submarine</div>
<div>Patch Name</div><div>Older Patch</div>
</body></html>
"""


def test_extract_latest_patch_stops_at_next_patch():
    patch = extract_latest_patch(HTML)
    assert patch.name == "February Update"
    assert patch.date == "2026-02-05"
    assert [section.title for section in patch.sections] == ["Features", "Fixed"]
    assert "Older Patch" not in " ".join(patch.sections[-1].items)


def test_image_matching_uses_text_and_fallback():
    sections = [
        PatchSection("Features", ["new fishing boat storage"]),
        PatchSection("Fixed", ["submarine crash"]),
    ]
    images = [
        ArticleImage("https://files.facepunch.com/fishing.jpg", "Fishing boat storage"),
        ArticleImage("https://files.facepunch.com/sub.jpg", "Submarine crash fix"),
    ]
    result = match_section_images(sections, images)
    assert result["Features"].endswith("fishing.jpg")
    assert result["Fixed"].endswith("sub.jpg")
