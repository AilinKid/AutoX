// Copyright 2026 AilinKid
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package domain

import (
	"errors"
	"time"
)

type EvidenceKind string

const (
	EvidenceSlowLog     EvidenceKind = "slow_log"
	EvidenceTopSQL      EvidenceKind = "top_sql"
	EvidenceMetric      EvidenceKind = "metric"
	EvidenceSchema      EvidenceKind = "schema"
	EvidenceStatistics  EvidenceKind = "statistics"
	EvidenceExplainPlan EvidenceKind = "explain_plan"
	EvidenceRuntimePlan EvidenceKind = "runtime_plan"
	EvidenceTiDBSource  EvidenceKind = "tidb_source"
	EvidenceExperiment  EvidenceKind = "experiment"
)

type Evidence struct {
	ID          string
	Kind        EvidenceKind
	Source      string
	CollectedAt time.Time
	Attributes  map[string]string
}

type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityLow      Severity = "low"
	SeverityMedium   Severity = "medium"
	SeverityHigh     Severity = "high"
	SeverityCritical Severity = "critical"
)

type Finding struct {
	ID          string
	Title       string
	Severity    Severity
	EvidenceIDs []string
	Confidence  float64
}

type RecommendationKind string

const (
	RecommendationBinding       RecommendationKind = "binding"
	RecommendationIndex         RecommendationKind = "index"
	RecommendationStatistics    RecommendationKind = "statistics"
	RecommendationRewrite       RecommendationKind = "sql_rewrite"
	RecommendationConfiguration RecommendationKind = "configuration"
	RecommendationRecovery      RecommendationKind = "recovery"
)

type Recommendation struct {
	ID             string
	Kind           RecommendationKind
	FindingIDs     []string
	Statement      string
	ExpectedImpact string
	Validation     ValidationResult
	Safety         SafetyAssessment
}

func (r Recommendation) ValidateForProduction() error {
	if !r.Validation.Reproduced {
		return errors.New("baseline behavior was not reproduced")
	}
	if !r.Safety.ProductionEligible {
		return errors.New("recommendation is not marked production eligible")
	}
	if !r.Safety.RequiresApproval {
		return errors.New("production action must require approval")
	}
	if !r.Safety.Reversible || r.Safety.RollbackStatement == "" {
		return errors.New("production action must be reversible and define rollback")
	}
	return nil
}

type ValidationResult struct {
	Reproduced        bool
	BaselinePlanHash  string
	CandidatePlanHash string
	Checks            []CheckResult
}

type CheckResult struct {
	Name    string
	Passed  bool
	Details string
}

type RiskLevel string

const (
	RiskReadOnly RiskLevel = "read_only"
	RiskLow      RiskLevel = "low"
	RiskMedium   RiskLevel = "medium"
	RiskHigh     RiskLevel = "high"
)

type SafetyAssessment struct {
	Risk               RiskLevel
	RequiresApproval   bool
	Reversible         bool
	RollbackStatement  string
	ProductionEligible bool
}

type Case struct {
	ID              string
	ClusterID       string
	TiDBVersion     string
	SQLDigest       string
	NormalizedSQL   string
	Evidence        []Evidence
	Findings        []Finding
	Recommendations []Recommendation
}
