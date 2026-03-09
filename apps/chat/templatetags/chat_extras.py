from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using a variable key."""
    if dictionary is None:
        print("Warning: get_item filter received None as dictionary")
        return None
    print(f"get_item called with dictionary: {dictionary}, key: {key}")
    return dictionary.get(key)
