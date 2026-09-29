# -*- coding: utf-8 -*-
from django.db import models
from django.forms import ModelForm
from flash.models import *

class ProfileForm(ModelForm):
  class Meta:
      model = Profile
      exclude = ('score', 'user',)
