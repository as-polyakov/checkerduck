import { useEffect, useState } from "react";
import AnalysisDashboard from "./pages/AnalysisDashboard";
import AnalysisResults from "./pages/AnalysisResults";
import { Analysis, AnalysisStatus, DomainData, DomainInput } from "./types";

// ===== API Configuration =====
const getApiBaseUrl = () => {
  // Get backend URL from environment variable
  const apiUrl = import.meta.env.VITE_API_URL;

  if (!apiUrl) {
    console.error("VITE_API_URL environment variable is not set!");
    throw new Error(
      "Backend API URL is not configured. Please set VITE_API_URL environment variable."
    );
  }

  console.log("Using backend API URL:", apiUrl);
  return apiUrl;
};

// ===== Main App with Navigation =====
export default function App() {
  const [currentView, setCurrentView] = useState<"dashboard" | "results">(
    "dashboard"
  );
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(
    null
  );
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [analysisResults, setAnalysisResults] = useState<DomainData[]>([]);
  const [isLoadingResults, setIsLoadingResults] = useState(false);

  // Fetch analyses from API only when on dashboard view
  useEffect(() => {
    if (currentView === "dashboard") {
      fetchAnalyses();

      // Refresh analyses every 2 seconds to see status updates
      const refreshInterval = setInterval(fetchAnalyses, 2000);

      return () => clearInterval(refreshInterval);
    }
  }, [currentView]);

  const fetchAnalyses = async () => {
    try {
      const apiBaseUrl = getApiBaseUrl();
      console.log("fetchAnalyses - API Base URL:", apiBaseUrl);
      const fetchUrl = `${apiBaseUrl}/api/analyses`;
      console.log("fetchAnalyses - Fetching from:", fetchUrl);

      const response = await fetch(fetchUrl);
      console.log("fetchAnalyses - Response status:", response.status);

      if (response.ok) {
        const data = await response.json();
        console.log("fetchAnalyses - Received data:", data);

        // Convert API response to frontend format
        const analysesData: Analysis[] = data.analyses.map((a: any) => {
          console.log(
            "Processing analysis:",
            a.id,
            "status:",
            a.status,
            "type:",
            typeof a.status
          );
          return {
            id: a.id,
            name: a.name,
            status: a.status as AnalysisStatus,
            createdAt: new Date(a.created_at),
            completedAt: a.completed_at ? new Date(a.completed_at) : undefined,
            totalDomains: a.total_domains,
            domainsAnalyzed: a.domains_analyzed || 0,
          };
        });

        console.log("fetchAnalyses - Processed analyses:", analysesData.length);
        setAnalyses(analysesData);
        setIsLoading(false);
      } else {
        console.error("fetchAnalyses - Response not OK:", response.statusText);
        const errorText = await response.text();
        console.error("fetchAnalyses - Error body:", errorText);
      }
    } catch (error) {
      console.error("Error fetching analyses:", error);
      console.error(
        "Error details:",
        error instanceof Error ? error.message : String(error)
      );
      setIsLoading(false);
    }
  };

  const fetchAnalysisResults = async (analysisId: string) => {
    console.log("=== fetchAnalysisResults called ===");
    console.log("Analysis ID:", analysisId);
    setIsLoadingResults(true);
    try {
      const apiBaseUrl = getApiBaseUrl();
      const fetchUrl = `${apiBaseUrl}/api/analyses-results/${analysisId}`;
      console.log("fetchAnalysisResults - Fetching from:", fetchUrl);

      const response = await fetch(fetchUrl);
      console.log("fetchAnalysisResults - Response status:", response.status);

      if (response.ok) {
        const data = await response.json();
        console.log("fetchAnalysisResults - Received data:", data);

        // Transform API response to DomainData format
        const domainResults: DomainData[] = data.domain_results.map(
          (dr: any, index: number) => {
            // Extract scores from rules_results (convert 0-1 scale to 0-100)
            const scores = {
              overall: Math.round((dr.rules_results.overall?.score || 0) * 100),
              DomainRatingRule: Math.round(
                (dr.rules_results.DomainRatingRule?.score || 0) * 100
              ),
              OrganicTrafficRule: Math.round(
                (dr.rules_results.OrganicTrafficRule?.score || 0) * 100
              ),
              HistoricalOrganicTrafficRule: Math.round(
                (dr.rules_results.HistoricalOrganicTrafficRule?.score || 0) *
                  100
              ),
              GeographyRule: Math.round(
                (dr.rules_results.GeographyRule?.score || 0) * 100
              ),
              DomainsInOutLinksRatioRule: Math.round(
                (dr.rules_results.DomainsInOutLinksRatioRule?.score || 0) * 100
              ),
              SingleTopPageTrafficRule: Math.round(
                (dr.rules_results.SingleTopPageTrafficRule?.score || 0) * 100
              ),
              ForbiddenWordsBacklinksRule: Math.round(
                (dr.rules_results.ForbiddenWordsBacklinksRule?.score || 0) * 100
              ),
              SpamWordsAnchorsRule: Math.round(
                (dr.rules_results.SpamWordsAnchorsRule?.score || 0) * 100
              ),
              ForbiddenWordsAnchorRule: Math.round(
                (dr.rules_results.ForbiddenWordsAnchorRule?.score || 0) * 100
              ),
              ForbiddenWordsOrganicKeywordsRule: Math.round(
                (dr.rules_results.ForbiddenWordsOrganicKeywordsRule?.score ||
                  0) * 100
              ),
              SpamWordsOrganicKeywordsRule: Math.round(
                (dr.rules_results.SpamWordsOrganicKeywordsRule?.score || 0) *
                  100
              ),
            };

            // Find all rules with critical violations
            const criticalViolations: string[] = [];
            Object.entries(dr.rules_results).forEach(
              ([ruleName, ruleData]: [string, any]) => {
                if (ruleData.critical_violation) {
                  // Convert camelCase to readable format
                  const readableName = ruleName
                    .replace(/Rule$/, "")
                    .replace(/([A-Z])/g, " $1")
                    .trim();
                  criticalViolations.push(readableName);
                }
              }
            );

            // Determine status based on critical violations
            const hasCriticalViolation =
              dr.rules_results.overall.critical_violation;
            const status = hasCriticalViolation
              ? "Reject"
              : scores.overall > 60
              ? "OK"
              : "Review";
            return {
              id: String(index + 1),
              domain: dr.domain,
              price: dr.price,
              scores,
              dr: dr.dr,
              org_traffic: dr.org_traffic,
              org_traffic_history: dr.org_traffic_history,
              geography: dr.geography,
              ld_lr_ratio: dr.ld_lr_ratio,
              top_page_traffic_pct: dr.top_page_traffic_pct,
              backlinks_forbidden_words: dr.backlinks_forbidden_words,
              anchors_forbidden_words: dr.anchors_forbidden_words,
              anchors_spam_words: dr.anchors_spam_words,
              organic_keywords_forbidden_words:
                dr.organic_keywords_forbidden_words,
              organic_keywords_spam_words: dr.organic_keywords_spam_words,
              status,
              criticalViolations:
                criticalViolations.length > 0 ? criticalViolations : undefined,
            };
          }
        );

        console.log(
          "fetchAnalysisResults - Processed domain results:",
          domainResults.length
        );
        setAnalysisResults(domainResults);
        setIsLoadingResults(false);
      } else {
        console.error(
          "fetchAnalysisResults - Response not OK:",
          response.statusText
        );
        const errorText = await response.text();
        console.error("fetchAnalysisResults - Error body:", errorText);
        setIsLoadingResults(false);
      }
    } catch (error) {
      console.error("=== Error in fetchAnalysisResults ===");
      console.error(
        "Error type:",
        error instanceof Error ? error.constructor.name : typeof error
      );
      console.error(
        "Error message:",
        error instanceof Error ? error.message : String(error)
      );
      console.error("Full error object:", error);
      setIsLoadingResults(false);
    }
  };

  const handleNewAnalysis = async (data: {
    name: string;
    domains: DomainInput[];
  }) => {
    console.log("=== handleNewAnalysis called ===");
    console.log("Analysis name:", data.name);
    console.log("Number of domains:", data.domains.length);
    console.log("Domains data:", JSON.stringify(data.domains, null, 2));

    try {
      // Call the backend API
      const apiBaseUrl = getApiBaseUrl();
      console.log("API Base URL:", apiBaseUrl);

      const requestUrl = `${apiBaseUrl}/api/startAnalysis`;
      console.log("Request URL:", requestUrl);

      const requestBody = {
        name: data.name,
        domains: data.domains,
      };
      console.log("Request body:", JSON.stringify(requestBody, null, 2));

      console.log("Sending POST request...");
      const response = await fetch(requestUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      console.log("Response status:", response.status);
      console.log("Response statusText:", response.statusText);
      console.log("Response ok:", response.ok);

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Error response body:", errorText);
        throw new Error(`API error: ${response.statusText} - ${errorText}`);
      }

      const responseData = await response.json();
      console.log("Success response data:", responseData);

      // Analysis created successfully - refresh the analyses list
      console.log("Refreshing analyses list...");
      await fetchAnalyses();
      console.log("Analysis created successfully!");

      // Note: The periodic refresh (every 2 seconds) will automatically
      // update the status as the analysis progresses
    } catch (error) {
      console.error("=== Error in handleNewAnalysis ===");
      console.error(
        "Error type:",
        error instanceof Error ? error.constructor.name : typeof error
      );
      console.error(
        "Error message:",
        error instanceof Error ? error.message : String(error)
      );
      console.error("Full error object:", error);

      if (error instanceof TypeError && error.message.includes("fetch")) {
        console.error("Network error - backend may not be reachable");
        alert(
          "Failed to connect to backend server. Please make sure:\n1. Backend server is running\n2. Backend is accessible at the API URL\n3. No CORS issues"
        );
      } else {
        alert(
          `Failed to create analysis: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
      }
    }
  };

  const handleSelectAnalysis = async (id: string) => {
    setSelectedAnalysisId(id);
    setCurrentView("results");
    // Fetch the analysis results
    await fetchAnalysisResults(id);
  };

  const handleBackToDashboard = () => {
    setCurrentView("dashboard");
    setSelectedAnalysisId(null);
    setAnalysisResults([]); // Clear results when going back
  };

  const selectedAnalysis = analyses.find((a) => a.id === selectedAnalysisId);

  if (currentView === "results" && selectedAnalysis) {
    // Use fetched analysis results or show loading state
    if (isLoadingResults) {
      return (
        <div className="min-h-screen bg-slate-50 flex items-center justify-center">
          <div className="text-center">
            <div className="text-lg font-medium text-slate-700">
              Loading analysis results...
            </div>
          </div>
        </div>
      );
    }

    // Use fetched results or show empty state
    const domainsToShow = analysisResults;

    return (
      <AnalysisResults
        analysisId={selectedAnalysis.id}
        onBack={handleBackToDashboard}
        DOMAINS={domainsToShow}
      />
    );
  }

  return (
    <AnalysisDashboard
      analyses={analyses}
      onNewAnalysis={handleNewAnalysis}
      onSelectAnalysis={handleSelectAnalysis}
      isLoading={isLoading}
    />
  );
}
