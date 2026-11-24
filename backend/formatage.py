"""Mise en forme des nombres pour l'affichage (format français : espace pour les milliers, virgule décimale)."""


def nombre(x: float) -> str:
    """Formate un nombre avec au plus une décimale, sans ``,0`` inutile.

    Args:
        x: nombre à formater.

    Returns:
        Le nombre en texte, par exemple ``1234.5 -> "1 234,5"`` et ``12.0 -> "12"``.
    """
    return f"{x:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0")


def pourcent(x: float) -> str:
    """Formate une proportion en pourcentage avec une décimale.

    Args:
        x: proportion, par exemple ``0.237``.

    Returns:
        Le pourcentage en texte, par exemple ``"23,7 %"``.
    """
    return f"{x:.1%}".replace(".", ",").replace("%", " %")


def eur(x: float) -> str:
    """Formate un montant en euros, arrondi à l'euro.

    Args:
        x: montant en €.

    Returns:
        Le montant en texte, par exemple ``123456.7 -> "123 457 €"``.
    """
    return f"{x:,.0f} €".replace(",", " ")
