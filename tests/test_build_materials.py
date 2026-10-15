from build_materials import clean_material, norm_id, split_claims


def test_norm_id_unifies_formats():
    assert norm_id("제2006-11호") == "2006-11"
    assert norm_id("New제2007-13호") == "2007-13"
    assert norm_id("2006-11") == "2006-11"


def test_clean_material_strips_recognition_suffix():
    assert clean_material("두충우슬추출복합물(KGC08EA)(제2023-40호)") == "두충우슬추출복합물(KGC08EA)"
    assert clean_material("바이오게르마늄 효모(기능성원료인정제2006-11호)") == "바이오게르마늄 효모"


def test_clean_material_strips_new_prefixed_suffix():
    assert clean_material("차조기등복합추출물(기능성원료인정New제2007-13호)") == "차조기등복합추출물"


def test_split_claims_keeps_korean_only_and_drops_grade_mark():
    assert split_claims("(국문) 관절 건강에 도움을 줄 수 있음(기타기능II) (영문) May help") == ["관절 건강에 도움을 줄 수 있음"]


def test_split_claims_reads_quoted_sentences():
    text = '"장내 유익균의 증식과 유해균의 억제에 도움을 줄 수 있습니다." “배변활동을 원활히 하는데 도움을 줄 수 있습니다.” (기타기능II)'
    assert split_claims(text) == ["장내 유익균의 증식과 유해균의 억제에 도움을 줄 수 있습니다",
                                  "배변활동을 원활히 하는데 도움을 줄 수 있습니다"]


def test_split_claims_empty_marker_gives_empty_list():
    assert split_claims(".") == []
