#!/bin/bash

# Function to display usage
function show_usage {
  echo "Usage: $0 [options]"
  echo "Options:"
  echo "  -v, --version-type TYPE   Version increment type (minor, patch). Default: patch"
  echo "  -d, --directory DIR       Base directory for prompts. Default: $HOME/gdk/gitlab-ai-gateway"
  echo "  -u, --suffix TYPE         Version suffix (dev, rc, alpha, beta). Makes version unstable."
  echo "  -s, --unstable            Mark as unstable version with default suffix (dev)"
  echo "  -h, --help                Show this help message"
  echo "Example:"
  echo "  $0                                 # Upgrades patch version as stable for all unit primitives"
  echo "  $0 -v minor                        # Upgrades minor version as stable for all unit primitives"
  echo "  $0 -u dev                          # Upgrades patch version with dev suffix"
  echo "  $0 -d /custom/path                 # Specify different base directory"
}

# Initialize default values
VERSION_TYPE="patch"
BASE_DIR="$HOME/gdk/gitlab-ai-gateway"
DEFINITIONS_PATH="ai_gateway/prompts/definitions"
IS_STABLE=true  # Default to stable versions
VERSION_SUFFIX="dev"  # Only used if IS_STABLE=false

# Parse command line arguments
while [ $# -gt 0 ]; do
  key="$1"
  case $key in
    -v|--version-type)
      VERSION_TYPE="$2"
      shift 2
      ;;
    -d|--directory)
      BASE_DIR="$2"
      shift 2
      ;;
    -s|--unstable)
      IS_STABLE=false
      shift
      ;;
    -u|--suffix)
      VERSION_SUFFIX="$2"
      IS_STABLE=false  # If a suffix is specified, it's not stable
      shift 2
      ;;
    -h|--help)
      show_usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      show_usage
      exit 1
      ;;
  esac
done

# Full path to definitions directory
DEFINITIONS_ROOT="$BASE_DIR/$DEFINITIONS_PATH"

# Check if version type is valid
if [ "$VERSION_TYPE" != "minor" ] && [ "$VERSION_TYPE" != "patch" ]; then
  echo "Error: Invalid version type. Use 'minor' or 'patch' only."
  exit 1
fi

# Check if suffix type is valid
if [ "$VERSION_SUFFIX" != "dev" ] && [ "$VERSION_SUFFIX" != "rc" ] && [ "$VERSION_SUFFIX" != "alpha" ] && [ "$VERSION_SUFFIX" != "beta" ]; then
  echo "Error: Invalid suffix type. Use 'dev', 'rc', 'alpha', or 'beta' only."
  exit 1
fi

# Check if definitions directory exists
if [ ! -d "$DEFINITIONS_ROOT" ]; then
  echo "Error: Definitions directory not found: $DEFINITIONS_ROOT"
  echo "Use -d option to specify the correct base directory where $DEFINITIONS_PATH exists."
  exit 1
fi

# Function to find all base YAML files recursively
function find_base_yml_files {
  local dir="$1"
  find "$dir" -path "*/base/*.yml" -type f | sort
}

# Extract unit primitives from directory structure, including subcategories
echo "Extracting unit primitives from directory structure (including subcategories)..."

# Get all base YAML files first
ALL_BASE_YAML_FILES=$(find_base_yml_files "$DEFINITIONS_ROOT")

if [ -z "$ALL_BASE_YAML_FILES" ]; then
  echo "Error: No base YAML files found in the definitions directory."
  exit 1
fi

# Extract the paths to create unit primitive identifiers
UNIT_PRIMITIVES=()

for yaml_file in $ALL_BASE_YAML_FILES; do
  # Get the relative path from the definitions root to the base directory
  rel_path=$(dirname $(dirname "$yaml_file"))
  rel_path=${rel_path#$DEFINITIONS_ROOT/}
  
  # This gives us something like "chat/write_tests" or just "merge_request_reader"
  if [[ ! " ${UNIT_PRIMITIVES[@]} " =~ " ${rel_path} " ]]; then
    UNIT_PRIMITIVES+=("$rel_path")
  fi
done

# Find all YAML files in base directories (including subcategories)
echo "Locating base directories for all unit primitives (including subcategories)..."

# Check if we found any unit primitives
if [ ${#UNIT_PRIMITIVES[@]} -eq 0 ]; then
  echo "Error: No unit primitives found in the directory structure."
  exit 1
fi

# Sort the unit primitives array
IFS=$'\n' SORTED_PRIMITIVES=($(sort <<<"${UNIT_PRIMITIVES[*]}"))
unset IFS

echo "Found ${#SORTED_PRIMITIVES[@]} unique unit primitives:"
for i in "${!SORTED_PRIMITIVES[@]}"; do
  echo "  $((i+1)). ${SORTED_PRIMITIVES[$i]}"
done

echo ""
echo "Will update version for all unit primitives:"
echo "- Version type: $VERSION_TYPE"
if [ "$IS_STABLE" = true ]; then
  echo "- Stable version (no suffix)"
else
  echo "- With suffix: -$VERSION_SUFFIX"
fi

# Confirm before proceeding
read -p "Continue? (y/n): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Operation cancelled."
  exit 0
fi

# Process each unit primitive
echo ""
echo "Updating prompt versions..."
for primitive in "${SORTED_PRIMITIVES[@]}"; do
  # For each unit primitive, construct the base directory path
  # Handle both top-level primitives and nested subcategories
  BASE_DIR="$DEFINITIONS_ROOT/$primitive/base"
  
  if [ ! -d "$BASE_DIR" ]; then
    echo "  No base directory found for unit primitive: $primitive, skipping."
    continue
  fi
  
  # Find all YAML files in the base directory
  YAML_FILES=$(find "$BASE_DIR" -type f -name "*.yml" | sort)
  
  if [ -z "$YAML_FILES" ]; then
    echo "  No YAML files found in base directory for: $primitive, skipping."
    continue
  fi
  
  # Display the primitive with proper formatting (using slash for subcategories)
  echo "  Processing unit primitive: $primitive"
  
  # Find the latest version file
  LATEST_FILE=""
  HIGHEST_VERSION="0.0.0"
  
  for file in $YAML_FILES; do
    filename=$(basename "$file")
    version_with_suffix=${filename%.yml}
    
    # Extract the version number without any suffix
    version=$(echo "$version_with_suffix" | sed -E 's/(-dev|-rc|-alpha|-beta)$//')
    
    # Check if the version follows semantic versioning pattern
    if echo "$version" | grep -q '^[0-9]\+\.[0-9]\+\.[0-9]\+$'; then
      # Compare versions using sort -V (version sort)
      if [ "$(printf '%s\n' "$HIGHEST_VERSION" "$version" | sort -V | tail -n1)" = "$version" ]; then
        HIGHEST_VERSION=$version
        LATEST_FILE=$file
      fi
    fi
  done
  
  if [ -z "$LATEST_FILE" ]; then
    echo "    Warning: Could not find a valid versioned file for $primitive, skipping."
    continue
  fi
  
  echo "    Found latest prompt definition: $(basename "$LATEST_FILE") (version $HIGHEST_VERSION)"
  
  # Extract version components
  MAJOR=$(echo "$HIGHEST_VERSION" | cut -d. -f1)
  MINOR=$(echo "$HIGHEST_VERSION" | cut -d. -f2)
  PATCH=$(echo "$HIGHEST_VERSION" | cut -d. -f3)
  
  # Increment version based on version type
  if [ "$VERSION_TYPE" = "minor" ]; then
    MINOR=$((MINOR + 1))
    PATCH=0
  else  # patch
    PATCH=$((PATCH + 1))
  fi
  
  # Create new version
  if [ "$IS_STABLE" = true ]; then
    NEW_VERSION="$MAJOR.$MINOR.$PATCH"
  else
    NEW_VERSION="$MAJOR.$MINOR.$PATCH-$VERSION_SUFFIX"
  fi
  
  # Use the full path for the new file
  NEW_FILE_PATH="$BASE_DIR/$NEW_VERSION.yml"
  
  # Copy file with new version
  cp "$LATEST_FILE" "$NEW_FILE_PATH"
  
  echo "    Created new version: $NEW_VERSION.yml from $(basename "$LATEST_FILE")"
done

echo ""
echo "Version update complete for all unit primitives!"