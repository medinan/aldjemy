from django.db import models
from django.contrib.postgres.fields import ArrayField


decimal_field = models.DecimalField(decimal_places=1, max_digits=3)


class TicTacToeBoard(models.Model):
    board = ArrayField(models.TextField(), size=9)
    array_of_decimals = ArrayField(decimal_field, size=9, null=True, blank=True)
