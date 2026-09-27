COPYFILE_DISABLE=1 tar --exclude='checkerduck/.venv' --exclude='checkerduck/frontend' --exclude='*/.*' --exclude='.DS_Store' --exclude=".git" -czf checkerduck.tar.gz checkerduck/
