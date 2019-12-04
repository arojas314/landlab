#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Base Species of SpeciesEvolver."""
from abc import ABC, abstractmethod


class Species(ABC):
    """Base Species of SpeciesEvolver.

    This class is intended to be subclassed to create species. Subclasses must
    implement the properties and methods of this base class that are designated
    as abstract.
    """
    def __init__(self):
        self._identifier = (None, None)
        self._parent_species = None

    @property
    def identifier(self):
        """The species identifier.

        The identifier is a two element tuple. The first element is the clade
        of the species represented by a string. The second element is the
        species number represented by an integer. The identifier is
        automatically generated by SpeciesEvolver.
        """
        return self._identifier

    @property
    def parent_species(self):
        """The parent species.

        The parent species is the species object that produced this species. A
        value of `None` indicates no parent species.
        """
        return self._parent_species

    @property
    @abstractmethod
    def range_mask(self):
        """A mask of the species geographic extent.

        This abstract method is intended to overridden in a subclass. The
        range mask is a boolean numpy array where True values indicate where
        the species is located in the model grid associated with a
        SpeciesEvolver instance.
        """
        # pragma: no cover

    @abstractmethod
    def _evolve_stage_1(self):
        """Run evolutionary processes in preperation of stage 2.

        SpeciesEvolver loops through extant species twice in the component's
        ``run_one_step`` method. Any processing that should be conducted upon
        all species before additional processing should be done in stage 1.
        """
        # pragma: no cover

    @abstractmethod
    def _evolve_stage_2(self):
        """Complete evolutionary processes for the time."""
        # pragma: no cover
