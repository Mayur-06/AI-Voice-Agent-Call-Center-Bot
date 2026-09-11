# Deliberately empty.
#
# Importing `app.main` here made every submodule import pull in the whole
# FastAPI application (and every one of its dependencies), which broke test
# collection and slowed startup. Import `app.main:app` explicitly instead.
