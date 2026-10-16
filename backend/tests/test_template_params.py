"""Every {{n}} in a broadcast template gets a value in its own position --
Meta rejects a send whose parameter count doesn't match the template."""
from app.services.template_params import body_parameters, template_var_count


def _texts(params):
    return [p["text"] for p in params]


def test_counts_the_highest_placeholder():
    assert template_var_count("Hi {{1}}, order {{2}} ships {{3}}") == 3
    assert template_var_count("No variables here") == 0
    assert template_var_count(None) == 0


def test_no_variables_sends_no_parameters():
    assert body_parameters("Hello there", ["name"], {"name": "Ravi"}, "Ravi") == []


def test_unmapped_variables_still_get_a_value_each():
    assert _texts(body_parameters("வணக்கம் {{1}}, {{2}}", [], {}, "Ravi")) == ["Ravi", "Customer"]


def test_mapping_only_the_second_variable_keeps_it_in_second_place():
    params = body_parameters("Hi {{1}}, your code is {{2}}", ["", "code"], {"code": "A7"}, "Ravi")
    assert _texts(params) == ["Ravi", "A7"]


def test_blank_csv_value_falls_back():
    params = body_parameters("Hi {{1}} {{2}}", ["name", "city"], {"name": "  ", "city": ""}, None)
    assert _texts(params) == ["Customer", "Customer"]
