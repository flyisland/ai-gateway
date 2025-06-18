GET_EPIC_NOTE_QUERY = """
    query GetEpicNote($id: NoteID!) {
      note(id: $id) {
        id
        body
        createdAt
        author {
          username
        }
      }
    }
    """

GET_EPIC_NOTES_QUERY = """
    query GetEpicNotes($fullPath: ID!, $epicIid: String!) {
      namespace(fullPath: $fullPath) {
        workItem(iid: $epicIid) {
          widgets {
            ... on WorkItemWidgetNotes {
              notes {
                nodes {
                  id
                  body
                  createdAt
                  author {
                    username
                  }
                }
              }
            }
          }
        }
      }
    }
    """
