"""Blog Visual Engine — block-based articles rendered once at publish time.

An article body is a JSON array of blocks (see schema.py), never HTML and
never markdown. Blocks are validated (validate.py), rendered to static HTML
with JSON-LD generated from the same blocks (render.py, seo.py), and written
to published/articles/<slug>/index.html for the marketing site to serve as a
file. The stylesheet is compiled from design_tokens.json (css.py) so the
dashboard preview and the public page cannot drift apart.

Everything here is pure Python with no database access, so it is testable
offline and the renderer can be re-run over every published article whenever
the page chrome or the tokens change.
"""
FEATURE_FLAG = "BLOG_ENGINE_V2"
