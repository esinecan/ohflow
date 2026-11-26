# Contracts

## find_user

`find_user(user_id: str) -> User | None` in `src/users.py` of the API. The step `api` owns it.
The client calls it only through `lib/lookup.py`, which the step `client` owns.
