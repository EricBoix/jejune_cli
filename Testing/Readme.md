# pdf-to-markdown testing

Integration tests for the [pdf-to-markdown](https://github.com/EricBoix/pdf-to-markdown) conversion pipeline across all [`jj_doc_*` repositories](./Makefile#1).

Each `jj_doc_*` repository holds both the source PDF and the Python code that converts it to Markdown,
building on the [pdf-to-markdown](https://github.com/EricBoix/pdf-to-markdown) library.
The tests here verify that the conversion output matches the expected reference data for each document.

## Running the tests

```bash
make
```

This clones (or pulls) each listed `jj_doc_*` repository into this directory, then runs its
`Convert/test_main.py` suite inside an isolated virtual environment.

Individual targets are also available:

```bash
make pull   # clone or update all repositories
make test   # run all test suites (implies pull)
```

Per-repository targets follow the pattern `pull-<repo>` and `test-<repo>`, e.g.:

```bash
make test-jj_doc_Collecting_Gold_Dust
make test-jj_doc_Zen_Flesh_Zen_Bones
```
