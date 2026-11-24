"""Mise en forme des nombres pour l'affichage (format français)."""


def nombre(x):
    return f"{x:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0")


def pourcent(x):
    return f"{x:.1%}".replace(".", ",").replace("%", " %")


def eur(x):
    return f"{x:,.0f} €".replace(",", " ")
