GET_EPIC_NOTE_QUERY = """
    query GetEpicNote($id: NoteID!) {
      note(id: $id) {
        id
        body
        author {
          username
        }
        createdAt
      }
    }
    """

LIST_EPIC_NOTES_QUERY = """
    query GetEpicNotes($fullPath: ID!, $epicIid: String!) {
      group(fullPath: $fullPath) {
        name
        workItem(iid: $epicIid) {
          widgets {
            ... on WorkItemWidgetNotes {
              type
              discussions {
                nodes {
                  notes {
                    edges {
                      node {
                        id
                        body
                        author {
                          username
                        }
                        createdAt
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
