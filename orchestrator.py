from utils import build_documents, fetch_opportunities


def main():

    # get opportunities from graphQL and write into data/opportunities.json
    fetch_opportunities()

    # build dict with metadata and embedding_text for each YOP, write into data/documents.json
    build_documents()
