# -*- coding: utf-8 -*-
def create_profile(sender, instance, signal, created, **kwargs):
    """When user is created also create a matching profile."""

    from flash.models import Profile

    if created:
        Profile(user = instance).save()
        # Do additional stuff here if needed, e.g.
        # create other required related records