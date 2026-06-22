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

package engine

import (
	"context"
	"fmt"

	"github.com/AilinKid/auto-sql-opt/internal/domain"
)

type EvidenceCollector interface {
	Collect(context.Context, domain.Case) ([]domain.Evidence, error)
}

type Analyzer interface {
	Analyze(context.Context, domain.Case) ([]domain.Finding, error)
}

type Recommender interface {
	Recommend(context.Context, domain.Case) ([]domain.Recommendation, error)
}

type Validator interface {
	Validate(context.Context, domain.Case, domain.Recommendation) (domain.ValidationResult, error)
}

type Engine struct {
	Collectors   []EvidenceCollector
	Analyzers    []Analyzer
	Recommenders []Recommender
	Validator    Validator
}

func (e Engine) Diagnose(ctx context.Context, diagnosisCase domain.Case) (domain.Case, error) {
	for _, collector := range e.Collectors {
		evidence, err := collector.Collect(ctx, diagnosisCase)
		if err != nil {
			return domain.Case{}, fmt.Errorf("collect evidence: %w", err)
		}
		diagnosisCase.Evidence = append(diagnosisCase.Evidence, evidence...)
	}

	for _, analyzer := range e.Analyzers {
		findings, err := analyzer.Analyze(ctx, diagnosisCase)
		if err != nil {
			return domain.Case{}, fmt.Errorf("analyze evidence: %w", err)
		}
		diagnosisCase.Findings = append(diagnosisCase.Findings, findings...)
	}

	for _, recommender := range e.Recommenders {
		recommendations, err := recommender.Recommend(ctx, diagnosisCase)
		if err != nil {
			return domain.Case{}, fmt.Errorf("generate recommendations: %w", err)
		}
		diagnosisCase.Recommendations = append(diagnosisCase.Recommendations, recommendations...)
	}

	if e.Validator == nil {
		return diagnosisCase, nil
	}

	for i := range diagnosisCase.Recommendations {
		result, err := e.Validator.Validate(ctx, diagnosisCase, diagnosisCase.Recommendations[i])
		if err != nil {
			return domain.Case{}, fmt.Errorf("validate recommendation %q: %w", diagnosisCase.Recommendations[i].ID, err)
		}
		diagnosisCase.Recommendations[i].Validation = result
	}

	return diagnosisCase, nil
}
