def pytest_addoption(parser):
    parser.addoption(
        "--req",  
        default="texte_reglementaire.txt",
        help="Chemin vers texte_reglementaire.txt"
    )
