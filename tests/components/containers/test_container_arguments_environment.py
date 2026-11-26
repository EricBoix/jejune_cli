from jejune_cli.components.containers.component_cont_convert import CompConvert

DEBUG_COMMENTS_OPTIONS = ["-e", "PDF_TO_MARKDOWN_DEBUG_COMMENTS=1"]


def test_test_run_has_no_debug_comments_by_default():
    arguments = CompConvert.container_arguments("image", test=True)
    assert arguments == ["docker", "run", "--rm", "image", "--test"]


def test_test_run_with_debug_comments_sets_the_variable_before_the_image():
    arguments = CompConvert.container_arguments(
        "image", test=True, with_debug_comments=True
    )
    assert arguments == [
        "docker",
        "run",
        "--rm",
        *DEBUG_COMMENTS_OPTIONS,
        "image",
        "--test",
    ]


def test_conversion_has_no_debug_comments_by_default(tmp_path):
    assert "-e" not in CompConvert.container_arguments("image", tmp_path)


def test_conversion_with_debug_comments_sets_the_variable(tmp_path):
    arguments = CompConvert.container_arguments(
        "image", tmp_path, with_debug_comments=True
    )
    assert arguments[:5] == ["docker", "run", "--rm", *DEBUG_COMMENTS_OPTIONS]
    assert arguments.index("image") > arguments.index("-e")
