from src.embeddings import (
    load_embeddings
)

from src.retriever import (
    load_vector_store
)


def search_repository(
        query,
        k=5
):

    embeddings = load_embeddings()

    vectordb = load_vector_store(
        embeddings
    )

    results = (
        vectordb.similarity_search(
            query,
            k=k
        )
    )

    return results


def main():

    while True:

        query = input(
            "\nAsk: "
        )

        if query.lower() == "exit":
            break

        results = search_repository(
            query
        )

        print("\nResults\n")

        for idx, result in enumerate(
                results,
                start=1
        ):

            print(
                "=" * 80
            )

            print(
                f"{idx}. "
                f"{result.metadata['file']}"
            )

            print(
                result.page_content[
                    :500
                ]
            )


if __name__ == "__main__":

    main()