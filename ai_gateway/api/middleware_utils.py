def get_valid_namespace_ids(ids: list[str]) -> list[int]:
    """Filter and convert string IDs to integers, removing any invalid values.

    Args:
        ids (list[str]): List of string IDs to filter and convert.

    Returns:
        A list of valid integer namespaces IDs.
    """
    valid_ids = []
    for str_id in ids:
        try:
            valid_ids.append(int(str_id))
        except ValueError:
            pass
    return valid_ids
