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
	"testing"

	"github.com/AilinKid/AutoX/internal/domain"
)

type collectorStub struct{}

func (collectorStub) Collect(context.Context, domain.Case) ([]domain.Evidence, error) {
	return []domain.Evidence{{ID: "slow-log-1", Kind: domain.EvidenceSlowLog}}, nil
}

type analyzerStub struct{}

func (analyzerStub) Analyze(context.Context, domain.Case) ([]domain.Finding, error) {
	return []domain.Finding{{ID: "finding-1", EvidenceIDs: []string{"slow-log-1"}}}, nil
}

type recommenderStub struct{}

func (recommenderStub) Recommend(context.Context, domain.Case) ([]domain.Recommendation, error) {
	return []domain.Recommendation{{ID: "recommendation-1", Kind: domain.RecommendationBinding}}, nil
}

type validatorStub struct{}

func (validatorStub) Validate(context.Context, domain.Case, domain.Recommendation) (domain.ValidationResult, error) {
	return domain.ValidationResult{Reproduced: true}, nil
}

func TestDiagnoseBuildsValidatedCase(t *testing.T) {
	e := Engine{
		Collectors:   []EvidenceCollector{collectorStub{}},
		Analyzers:    []Analyzer{analyzerStub{}},
		Recommenders: []Recommender{recommenderStub{}},
		Validator:    validatorStub{},
	}

	got, err := e.Diagnose(context.Background(), domain.Case{ID: "case-1"})
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Evidence) != 1 || len(got.Findings) != 1 || len(got.Recommendations) != 1 {
		t.Fatalf("unexpected diagnosis result: %+v", got)
	}
	if !got.Recommendations[0].Validation.Reproduced {
		t.Fatal("recommendation was not validated")
	}
}
