import { SearchForm } from "@/components/search/search-form";
import { PageHeader } from "@/components/ui/page-header";

export default function SearchPage() {
  return <><PageHeader title="Semantic search" description="Search only among problem posts already classified by unMeet." /><SearchForm /></>;
}
