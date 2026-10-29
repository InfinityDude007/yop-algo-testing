from utils import build_documents, fetch_opportunities, upload_documents


def main():

    # get opportunities from graphQL and write into data/opportunities.json
    fetch_opportunities()

    # build dict with metadata and embedding_text for each YOP, write into data/documents.json
    build_documents()

    # embed embedding_text with bedrock titan and upload to s3 vectors with metadata
    upload_documents()


if __name__ == "__main__":
    main()
